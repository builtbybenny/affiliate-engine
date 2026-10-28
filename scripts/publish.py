#!/usr/bin/env python3
"""Publish generated media to Instagram and Facebook.

Examples:
  python scripts/publish.py --today                # post what the calendar says
  python scripts/publish.py --today --ig-only      # only Instagram
  python scripts/publish.py --latest --fb-only     # push newest render to FB
  python scripts/publish.py --today --dry-run      # resolve URLs, don't post
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
import time
from datetime import date as _date
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console; setup_console()

from core import config, planner
from publishers import facebook, hosting, instagram
from publishers import youtube as yt_publisher

# Research provenance is grounding for the writer, never copy for the
# viewer — strip it defensively at publish time (generation strips too,
# but renders made before 2026-10-07 still carry notes).
_SOURCE_NOTE = re.compile(r"\s*\((?:source|src):\s*[^)]*\)", re.IGNORECASE)


def load_plan(for_date: _date, fmt: str) -> dict:
    """Plan for this slot, written by generate.py. Falls back gracefully."""
    plan_file = config.DATA_DIR / "plan.json"
    if plan_file.exists():
        try:
            import json

            for p in json.loads(plan_file.read_text(encoding="utf-8")):
                if p.get("date") == for_date.isoformat() and p.get("format") == fmt:
                    return p
        except Exception:
            pass
    return {"product_id": "", "concept": fmt, "is_rerun": False}


_LOG_HEADER = ["date", "format", "product_id", "ig_media_id", "fb_post_id", "yt_video_id", "media_urls"]


def _log_rows() -> list[list[str]]:
    """Rows of the publish log with any header/blank lines removed.

    The log used to grow a fresh header every time its first line looked old,
    which left header rows stranded between data rows (2026-10-28). Readers
    key on date/format so nothing broke, but one canonical header keeps every
    consumer — guard, insights, weekly review — honest.
    """
    if not config.PUBLISHED_LOG.exists():
        return []
    rows: list[list[str]] = []
    with open(config.PUBLISHED_LOG, newline="", encoding="utf-8") as f:
        for row in csv.reader(f):
            if not row or row[:2] == _LOG_HEADER[:2]:
                continue
            rows.append((row + [""] * len(_LOG_HEADER))[: len(_LOG_HEADER)])
    return rows


def log_published(for_date: _date, fmt: str, product_id: str, ig_id: str, fb_id: str, urls: list[str], yt_id: str = "") -> None:
    rows = _log_rows()
    rows.append([for_date.isoformat(), fmt, product_id, ig_id, fb_id, yt_id, "|".join(urls)])
    with open(config.PUBLISHED_LOG, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(_LOG_HEADER)
        w.writerows(rows)


def already_published(for_date: _date, fmt: str) -> bool:
    """True when this slot already has a live post.

    Retries are the reason this exists: each scheduled trigger re-renders and
    would happily publish a second carousel for the same day, spending the
    app's request quota on a duplicate.
    """
    target = for_date.isoformat()
    return any(row[0] == target and row[1] == fmt for row in _log_rows())


def latest_render(fmt: str) -> Path | None:
    base = config.CAROUSELS_DIR if fmt == "carousel" else config.REELS_DIR
    # A GitHub Actions checkout stamps EVERY file with the same mtime, so
    # mtime alone is meaningless in CI: tie-break on the path. Our render
    # folders are date-named (YYYY-MM-DD), so among equal mtimes the
    # lexicographically greatest path IS the newest render — the repo's own
    # "pick newest by path" rule, which this function used to violate.
    candidates = sorted(
        base.glob("**/*"), key=lambda p: (p.stat().st_mtime, p.as_posix()), reverse=True
    )
    if fmt == "carousel":
        for c in candidates:
            if c.is_dir() and list(c.glob("slide_*.jpg")):
                return c
    else:
        for c in candidates:
            if c.is_file() and c.suffix == ".mp4":
                return c
    return None


def token_has_scope(scope: str) -> bool:
    """True if the page token carries this permission (debug_token, app token).
    Unknown (no app creds / network hiccup) -> False, so we take the safe
    fallback of folding hashtags into the caption."""
    app_id = os.getenv("META_APP_ID", "")
    app_secret = os.getenv("META_APP_SECRET", "")
    if not (app_id and app_secret and config.ACCESS_TOKEN):
        return False
    try:
        r = requests.get(
            f"https://graph.facebook.com/{config.GRAPH_VERSION}/debug_token",
            params={
                "input_token": config.ACCESS_TOKEN,
                "access_token": f"{app_id}|{app_secret}",
            },
            timeout=15,
        )
        return scope in r.json().get("data", {}).get("scopes", [])
    except Exception:
        return False


def wait_for_media(urls: list[str], timeout: int = 900, fatal: bool = True) -> bool:
    """Block until every media URL is publicly served WITH a media content-type.

    Meta fetches these URLs itself. If GitHub Pages has not deployed them
    yet, Meta receives an HTML 404 page instead of a JPEG/MP4 and answers
    error 9004 "Only photo or video can be accepted as media type" — every
    morning carousel failure from 2026-10-21 to 2026-10-24 was exactly this
    race (the workflow's Pages check was looking at an OLD reel file, so it
    returned "served" instantly and publishing ran ahead of the deploy).

    Check the precise URLs we are about to hand to the Graph API, right
    before we hand them over, rather than trusting a generic deploy check.
    """
    deadline = time.time() + timeout
    pending = list(urls)
    while pending:
        still: list[str] = []
        for u in pending:
            if not _served_as_media(u):
                still.append(u)
        if not still:
            print(f"  media live: all {len(urls)} URL(s) served as media")
            return True
        if time.time() >= deadline:
            msg = f"media not publicly served after {timeout}s: {still[0]}"
            if fatal:
                raise SystemExit(msg)
            print(f"  ({msg})")
            return False
        pending = still
        time.sleep(15)
    return True


def _served_as_media(url: str) -> bool:
    """True when the URL answers 200 with image/* or video/*."""
    try:
        r = requests.head(url, timeout=15, allow_redirects=True)
        if r.status_code == 405 or r.status_code == 501:  # some CDNs refuse HEAD
            r = requests.get(url, timeout=20, allow_redirects=True, stream=True)
            r.close()
        ctype = (r.headers.get("content-type") or "").lower()
        return r.status_code == 200 and ("image/" in ctype or "video/" in ctype)
    except Exception:
        return False


def publish(fmt: str, for_date: _date, dry_run: bool, targets: set[str],
             force: bool = False) -> None:
    if not dry_run and not force and already_published(for_date, fmt):
        print(f"[{fmt}] {for_date} is already published — nothing to do (use --force to override)")
        return
    products = planner.load_products()
    plan = load_plan(for_date, fmt)
    product = (
        planner.find_by_slug(plan["product_id"], products)
        if plan.get("product_id")
        else planner.pick_product(for_date, fmt, products)
    ) or planner.pick_product(for_date, fmt, products)
    pid = planner.slugify(product.get("id") or product["name"])
    concept_label = plan.get("concept", fmt)

    cap_file = None
    if fmt == "carousel":
        render = latest_render("carousel") or None
        if render is None:
            raise SystemExit("No carousel found. Run scripts/generate.py first.")
        slides = sorted(render.glob("slide_*.jpg"))
        cap_file = render / "caption.txt"
        if not cap_file.exists():
            cap_file = render / "slides.txt"
        caption = (
            cap_file.read_text(encoding="utf-8")
            if cap_file.exists()
            else product["name"]
        )
        urls = [hosting.media_url(s) for s in slides]
    else:
        render = latest_render("reel")
        if render is None:
            raise SystemExit("No reel found. Run scripts/generate.py first.")
        cap_file = render.with_name(render.stem + "_caption.txt")
        caption = (
            cap_file.read_text(encoding="utf-8")
            if cap_file.exists()
            else product["name"]
        )
        urls = [hosting.media_url(render)]

    caption = _SOURCE_NOTE.sub("", caption).strip()

    print(f"[{fmt}] concept={concept_label} product={product['name']}")
    for u in urls:
        print("  URL:", u)

    # Auto first comment (hashtags). File may not exist on older renders.
    if fmt == "carousel":
        comment_file = render / "first_comment.txt"
    else:
        comment_file = render.with_name(render.stem + "_comment.txt")
    first_comment = (
        comment_file.read_text(encoding="utf-8") if comment_file.exists() else ""
    )

    # Hashtag strategy. IG captions are immutable after publishing, so decide
    # NOW: if the token lacks instagram_manage_comments, fold the hashtag
    # block into the caption instead of losing it. FB has no first-comment
    # flow in this engine, so hashtags always ride in the FB caption.
    hashtags = first_comment.strip()
    ig_can_comment = token_has_scope("instagram_manage_comments") if hashtags else True
    if hashtags and not ig_can_comment:
        print("  (no comment permission on token: hashtags folded into caption)")
    caption_ig = caption + (f"\n\n{hashtags}" if hashtags and not ig_can_comment else "")
    caption_fb = caption + (f"\n\n{hashtags}" if hashtags else "")

    if dry_run:
        # Offline-friendly: report readiness, never block a dry run.
        wait_for_media(urls, timeout=3, fatal=False)
        print("(dry run — nothing posted)")
        return

    # Hard gate: never send Meta a URL GitHub Pages has not published yet.
    wait_for_media(urls)

    ig_id = fb_id = ""
    if "ig" in targets:
        if fmt == "carousel":
            ig_id = instagram.publish_carousel(urls, caption_ig)
        elif fmt == "reel":
            ig_id = instagram.publish_reel(urls[0], caption_ig)
        print("  IG published:", ig_id)
        if first_comment and ig_can_comment:
            cid = instagram.post_first_comment(ig_id, first_comment)
            if cid:
                print("  IG first comment posted")
    if "fb" in targets:
        if fmt == "reel":
            fb_id = facebook.publish_video(urls[0], caption_fb)
        else:
            fb_id = facebook.publish_photo(urls[0], caption_fb)
        print("  FB published:", fb_id)

    yt_id = ""
    if "yt" in targets and fmt == "reel":
        yt_title = product["name"] + " — " + caption.splitlines()[0][:60]
        yt_id = yt_publisher.publish_short(str(render), f"{yt_title}\n\n{caption_fb}")
        print("  YT published:", yt_id)

    log_published(for_date, fmt, pid, ig_id, fb_id, urls, yt_id)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--date", type=str, default="")
    ap.add_argument("--latest", action="store_true", help="publish most recent render")
    ap.add_argument("--format", choices=["carousel", "reel"], default="")
    ap.add_argument("--ig-only", action="store_true")
    ap.add_argument("--fb-only", action="store_true")
    ap.add_argument("--yt-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="publish even if this slot is already logged")
    args = ap.parse_args()

    for_date = (
        _date.fromisoformat(args.date) if args.date else config.now_local().date()
    )
    targets = (
        {"ig"} if args.ig_only
        else {"fb"} if args.fb_only
        else {"yt"} if args.yt_only
        else {"ig", "fb"}
    )

    if args.format:
        publish(args.format, for_date, args.dry_run, targets, force=args.force)
    else:
        day_entries = config.WEEKLY_CALENDAR.get(for_date.strftime("%a").lower(), [])
        fmts = [f for f, _ in day_entries] or ["carousel"]
        if args.latest:
            fmts = ["carousel" if latest_render("carousel") else "reel"]
        for fmt in fmts:
            publish(fmt, for_date, args.dry_run, targets, force=args.force)


if __name__ == "__main__":
    main()
