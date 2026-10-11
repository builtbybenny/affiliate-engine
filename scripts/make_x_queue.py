#!/usr/bin/env python3
"""Build the manual X-posting queue from published IG/FB content.

X API posting costs money per post ($0.015 plain / $0.20 with a URL — no free
write tier since 2023), so the X channel runs MANUAL for now: this script
stages ready-to-paste posts into public/x/ (copied to docs/x/ by the same
flow that mirrors public/media into docs/), one file per published post plus
a running INDEX.md that maps date -> posts -> media files.

X-specific optimization (280-char cap, no newline-heavy IG style):
- lead line = published hook (already punch-gated)
- body line = one benefit/number from the caption (first bullet or first
  sentence after the hook, stripped of IG-only formatting)
- last line = fixed "Free trial: <bio-page url>" mention — the page IS the
  affiliate surface, disclosed by name, so every post stays honest without
  burning chars on link shorteners.

Usage:
  python scripts/make_x_queue.py                 # today's published post
  python scripts/make_x_queue.py --backfill 14   # last 14 days from the log
  python scripts/make_x_queue.py --date 2026-10-11
"""
from __future__ import annotations

import argparse
import csv
import re
import shutil
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console; setup_console()

from core import config, planner

BIO_URL = config.PUBLIC_BASE_URL or "https://builtbybenny.github.io/affiliate-engine"

# X queue lives beside the other public surfaces (link-bio, media) so the
# CI docs/ mirror picks it up automatically — same hosting, $0.
X_DIR = config.PUBLIC_DIR / "x"
X_DOCS_DIR = config.ROOT / "docs" / "x"

INDEX_HEADER = (
    "# X posting queue — manual posting log\n\n"
    "One block per published IG/FB post. Paste the POST text into X, attach\n"
    "the media file(s) listed, then tick the checkbox and date it. Delete a\n"
    "post here once it's live on X (or leave for the record — your call).\n\n"
    "Posts are pre-optimized for X: under 280 chars, hook first, one number,\n"
    "bio-page mention instead of raw affiliate links (API rules for posted\n"
    "URLs don't apply to text-only mentions, and it reads cleaner).\n\n"
    "---\n\n"
)


def _latest_caption_text(date_iso: str, fmt: str, product_id: str) -> str:
    """Caption of the published post, from the docs/ mirror (has CI pushes)."""
    base = config.ROOT / "docs" / "media"
    if fmt == "carousel":
        d = base / "carousels" / f"{date_iso}_carousel_{product_id}"
        return (d / "caption.txt").read_text(encoding="utf-8") if d.exists() else ""
    f = base / "reels" / f"{date_iso}_reel_{product_id}_caption.txt"
    return f.read_text(encoding="utf-8") if f.exists() else ""


def _media_files(date_iso: str, fmt: str, product_id: str) -> list[Path]:
    """Published media files for this post (carousel slides / reel mp4)."""
    base = config.ROOT / "docs" / "media"
    if fmt == "carousel":
        d = base / "carousels" / f"{date_iso}_carousel_{product_id}"
        return sorted(d.glob("slide_*.jpg")) if d.exists() else []
    f = base / "reels" / f"{date_iso}_reel_{product_id}.mp4"
    return [f] if f.exists() else []


# X-style weighted length: non-ASCII counts 2, bare domains count as a
# 23-char t.co link regardless of real length. Kept as pure helpers so the
# trimmer and the assert share one definition of "how long is this post".
_URL_RE = re.compile(r"(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/\S*)?", re.IGNORECASE)


def _weighted(s: str) -> int:
    return sum(2 if ord(ch) > 127 else 1 for ch in _URL_RE.sub("", s))


def _weighted_post(s: str) -> int:
    return _weighted(s) + 23 * len(_URL_RE.findall(s))


def _trim_weighted(s: str, budget: int) -> str:
    """Cut s to `budget` weighted chars on a word boundary, ellipsised."""
    while _weighted(s) > budget - 1 and s:
        s = s[: len(s) - 1]
    s = s.rstrip()
    return s + "…" if s else ""


def optimize_post(caption: str, product_name: str, fmt: str) -> tuple[str, str]:
    """Render the IG caption into one X post. Returns (post_text, warning|'').

    Shape: hook (line 1) -> one concrete benefit/number line -> free-trial
    bio mention. Hard target: <= 280 chars; suggests trimming if over.
    """
    name = product_name  # short alias used by the fallback body below
    lines = [l.strip() for l in caption.splitlines() if l.strip()]
    hook = lines[0] if lines else product_name
    # first bullet or second sentence as the benefit line
    body = ""
    for l in lines[1:]:
        if l.startswith("•"):
            body = l.lstrip("• ").strip()
            break
        if len(l.split()) >= 4 and "source:" not in l.lower():
            body = l
            break
    if not body:
        body = lines[-1] if len(lines) > 1 else ""
        body = body.strip("• ").strip()
    # IG-style artifacts X readers won't parse
    body = body.replace(" | ", " — ").strip()
    if len(body) > 140:  # keep the whole post compact
        body = body[:137].rstrip() + "…"
    tag = "🎬 60-second breakdown" if fmt == "reel" else "📊 4-slide breakdown"
    tail = f"{tag} on the site — free trial: {BIO_URL.replace('https://', '')}"
    # X's weighted counter: non-ASCII = 2, bare domains count as a 23-char
    # t.co link regardless of real length. Budget hook+body against the
    # weighted remainder so the final post is ALWAYS <= 280 weighted.
    domain = BIO_URL.replace("https://", "")
    tail_weighted = _weighted(tail.replace(domain, "")) + 23 - 1  # -1: trailing-space edge
    budget = 280 - tail_weighted - 2  # 2 newlines between the three lines
    hook_fit = hook if _weighted(hook) <= budget else _trim_weighted(hook, budget)
    body_budget = budget - _weighted(hook_fit) - 2
    body_fit = ""
    if body_budget > 4:
        body_fit = (_trim_weighted(body, body_budget)
                    if len(body) > body_budget else body)
    # No room for a body after the hook? Post hook + tail only — the old
    # fallback ("X does it all in one tab.") ignored the budget and could
    # push the total past 280 (2026-10-11 pictory regression).
    text = (
        f"{hook_fit}\n{body_fit}\n{tail}" if body_fit
        else f"{hook_fit}\n{tail}"
    )
    warning = ""
    if _weighted_post(text) > 280:
        warning = f"OVER 280 ({len(text)}) — trim the middle line"
    return text, warning


def write_day(date_iso: str, rows: list[dict]) -> list[str]:
    """Emit one .txt per published post for this date; returns filenames."""
    written: list[str] = []
    X_DIR.mkdir(parents=True, exist_ok=True)
    for r in rows:
        fmt, pid = r["format"], r["product_id"]
        cap = _latest_caption_text(date_iso, fmt, pid)
        if not cap:
            print(f"  [{date_iso}] {fmt}/{pid}: caption missing, skipped")
            continue
        product = planner.find_by_slug(pid, planner.load_products())
        name = product["name"] if product else pid.title()
        text, warn = optimize_post(cap, name, fmt)
        fname = f"{date_iso}_{fmt}_{pid}.txt"
        (X_DIR / fname).write_text(text, encoding="utf-8")
        # media next to it: reel mp4 or the whole carousel slide set
        media = _media_files(date_iso, fmt, pid)
        if fmt == "reel":
            for m in media:
                shutil.copy2(m, X_DIR / m.name)
        else:
            for m in media:
                dest = X_DIR / f"{date_iso}_{fmt}_{pid}" / m.name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(m, dest)
        note = f"  [{date_iso}] {fmt}/{pid}: {fname} ({len(text)} chars"
        note += f", {len(media)} media file(s)"
        if warn:
            note += f", WARNING: {warn}"
        print(note + ")")
        written.append(fname)
    return written


def rebuild_index() -> None:
    """One running doc mapping every queued post: date -> files -> media."""
    blocks: list[str] = []
    by_date: dict[str, list[Path]] = defaultdict(list)
    for f in sorted(X_DIR.glob("*.txt")):
        date_iso = f.name[:10]
        by_date[date_iso].append(f)
    for date_iso in sorted(by_date, reverse=True):
        parts = [f"## {date_iso}\n"]
        for f in by_date[date_iso]:
            stem = f.stem
            fmt = "reel" if "_reel_" in stem else "carousel"
            pid = stem.split(f"_{fmt}_", 1)[1]
            text = f.read_text(encoding="utf-8")
            # media hint mirrors what write_day actually staged (mp4 file or
            # a slide-folder named <date>_<fmt>_<pid>/)
            if fmt == "reel":
                media_hint = f"media: {f.stem}.mp4"
            else:
                media_hint = f"media: {stem}/ (slide_01.jpg …)"
            parts.append(
                f"### {pid} ({fmt}) — [ ] paste + attach + post\n\n"
                f"```\n{text}\n```\n"
                f"^{media_hint}^\n"
            )
        blocks.append("\n".join(parts))
    index = INDEX_HEADER + "\n\n".join(blocks)
    (X_DIR / "INDEX.md").write_text(index, encoding="utf-8")
    # mirror to docs/ (Pages serves it; same rsync rule as public/media)
    if X_DOCS_DIR.exists() is False:
        X_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    shutil.copy2(X_DIR / "INDEX.md", X_DOCS_DIR / "INDEX.md")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", type=str, default="")
    ap.add_argument("--backfill", type=int, default=0, help="days back from newest log row")
    args = ap.parse_args()

    with open(config.PUBLISHED_LOG, newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("date")]

    if not rows:
        raise SystemExit("published_log.csv empty — nothing to queue")

    if args.date:
        days = [args.date]
    elif args.backfill:
        newest = max(r["date"] for r in rows)
        newest_d = __import__("datetime").date.fromisoformat(newest)
        days = [(newest_d - timedelta(days=i)).isoformat() for i in range(args.backfill)]
    else:
        days = [max(r["date"] for r in rows)]  # today/latest

    for day in days:
        day_rows = [r for r in rows if r["date"] == day]
        if not day_rows:
            print(f"  [{day}] not in published log, skipped")
            continue
        write_day(day, day_rows)
    rebuild_index()
    print(f"\nQueue: {X_DIR}  (INDEX.md maps every post + its media)")


if __name__ == "__main__":
    main()
