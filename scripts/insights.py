#!/usr/bin/env python3
"""Weekly performance report: followers, last posts' engagement, best formats.

  python scripts/insights.py            # last 7 days
  python scripts/insights.py --days 30
"""
from __future__ import annotations

import argparse
import csv
import sys
from collections import defaultdict
from datetime import timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console; setup_console()

from core import config


def fetch_account() -> dict:
    r = requests.get(
        f"https://graph.facebook.com/{config.GRAPH_VERSION}/{config.IG_USER_ID}",
        params={
            "fields": "username,followers_count,media_count",
            "access_token": config.ACCESS_TOKEN,
        },
        timeout=30,
    ).json()
    return r


def fetch_recent_media(limit: int = 25) -> list[dict]:
    r = requests.get(
        f"https://graph.facebook.com/{config.GRAPH_VERSION}/{config.IG_USER_ID}/media",
        params={
            "fields": "id,caption,timestamp,media_type,like_count,comments_count",
            "access_token": config.ACCESS_TOKEN,
            "limit": limit,
        },
        timeout=30,
    ).json()
    return r.get("data", [])


def fetch_retention(media: list[dict]) -> list[dict]:
    """Per-reel retention: views + total watch time -> avg seconds/view.

    Needs the instagram_manage_insights scope (token re-minted 2026-10-05).
    Graph API exposes no skip-rate metric — avg watch time is the
    programmatic proxy (skip rate stays an IG-app reading).
    """
    out: list[dict] = []
    for m in media:
        if m.get("media_type") not in ("REELS", "VIDEO"):
            continue
        try:
            r = requests.get(
                f"https://graph.facebook.com/{config.GRAPH_VERSION}/{m['id']}/insights",
                params={"metric": "views,ig_reels_video_view_total_time",
                        "access_token": config.ACCESS_TOKEN},
                timeout=20,
            ).json()
            # Graph API labels each block with "name" (not "metric")
            vals = {d.get("name"): d.get("values", [{}])[0].get("value")
                    for d in r.get("data", [])}
        except Exception:
            continue
        views = int(vals.get("views") or 0)
        total_ms = int(vals.get("ig_reels_video_view_total_time") or 0)
        if views:
            out.append({
                "date": m.get("timestamp", "")[:10],
                "views": views,
                "avg_watch_s": round(total_ms / 1000 / views, 1),
            })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()

    print("=" * 60)
    print(f" Weekly insights ({args.days} days)")
    print("=" * 60)

    try:
        acct = fetch_account()
        print(f"Account : @{acct.get('username')}")
        print(f"Followers: {acct.get('followers_count')}   Posts: {acct.get('media_count')}")
    except Exception as e:
        print(f"(account fetch skipped: {e})")

    try:
        media = fetch_recent_media()
        cutoff = (config.now_local() - timedelta(days=args.days)).date()
        rows = [m for m in media if m.get("timestamp", "")[:10] >= cutoff.isoformat()]
        if rows:
            print(f"\n{len(rows)} posts in window:")
            for m in rows:
                cap = (m.get("caption") or "").splitlines()[0][:48]
                likes, comments = m.get("like_count", 0), m.get("comments_count", 0)
                print(f"  {m['timestamp'][:10]}  {m.get('media_type','?'):<10} ♥{likes:<5} 💬{comments:<4} {cap}")
            best = max(rows, key=lambda m: m.get("like_count", 0) + 3 * m.get("comments_count", 0))
            print(f"\nTop post: {best.get('caption', '').splitlines()[0][:60]}")
            ret = fetch_retention(rows)
            if ret:
                print("\nRetention (reels, avg watch time per view):")
                for r in ret:
                    print(f"  {r['date']}  views {r['views']:<4} avg {r['avg_watch_s']}s")
            else:
                print("\n(no reel retention data — needs instagram_manage_insights scope)")
        else:
            print("\nNo posts in the window.")
    except Exception as e:
        print(f"(media fetch skipped: {e})")

    if config.PUBLISHED_LOG.exists():
        with open(config.PUBLISHED_LOG, encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        by_fmt = defaultdict(int)
        for r in rows[-60:]:
            by_fmt[r["format"]] += 1
        print("\nPublished (last 60 rows): " + ", ".join(f"{k}={v}" for k, v in by_fmt.items()))


if __name__ == "__main__":
    main()
