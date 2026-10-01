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
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console; setup_console()

from core import config, planner
from publishers import facebook, hosting, instagram


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


def log_published(for_date: _date, fmt: str, product_id: str, ig_id: str, fb_id: str, urls: list[str]) -> None:
    new = not config.PUBLISHED_LOG.exists()
    with open(config.PUBLISHED_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["date", "format", "product_id", "ig_media_id", "fb_post_id", "media_urls"])
        w.writerow([for_date.isoformat(), fmt, product_id, ig_id, fb_id, "|".join(urls)])


def latest_render(fmt: str) -> Path | None:
    base = config.CAROUSELS_DIR if fmt == "carousel" else config.REELS_DIR
    candidates = sorted(base.glob("**/*"), key=lambda p: p.stat().st_mtime, reverse=True)
    if fmt == "carousel":
        for c in candidates:
            if c.is_dir() and list(c.glob("slide_*.jpg")):
                return c
    else:
        for c in candidates:
            if c.is_file() and c.suffix == ".mp4":
                return c
    return None


def publish(fmt: str, for_date: _date, dry_run: bool, targets: set[str]) -> None:
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

    if dry_run:
        print("(dry run — nothing posted)")
        return

    ig_id = fb_id = ""
    if "ig" in targets:
        if fmt == "carousel":
            ig_id = instagram.publish_carousel(urls, caption)
        elif fmt == "reel":
            ig_id = instagram.publish_reel(urls[0], caption)
        print("  IG published:", ig_id)
        if first_comment:
            cid = instagram.post_first_comment(ig_id, first_comment)
            if cid:
                print("  IG first comment posted")
    if "fb" in targets:
        if fmt == "reel":
            fb_id = facebook.publish_video(urls[0], caption)
        else:
            fb_id = facebook.publish_photo(urls[0], caption)
        print("  FB published:", fb_id)

    log_published(for_date, fmt, pid, ig_id, fb_id, urls)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--date", type=str, default="")
    ap.add_argument("--latest", action="store_true", help="publish most recent render")
    ap.add_argument("--format", choices=["carousel", "reel"], default="")
    ap.add_argument("--ig-only", action="store_true")
    ap.add_argument("--fb-only", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for_date = (
        _date.fromisoformat(args.date) if args.date else config.now_local().date()
    )
    targets = {"ig"} if args.ig_only else {"fb"} if args.fb_only else {"ig", "fb"}

    if args.format:
        publish(args.format, for_date, args.dry_run, targets)
    else:
        day_entries = config.WEEKLY_CALENDAR.get(for_date.strftime("%a").lower(), [])
        fmts = [f for f, _ in day_entries] or ["carousel"]
        if args.latest:
            fmts = ["carousel" if latest_render("carousel") else "reel"]
        for fmt in fmts:
            publish(fmt, for_date, args.dry_run, targets)


if __name__ == "__main__":
    main()
