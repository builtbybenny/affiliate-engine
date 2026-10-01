#!/usr/bin/env python3
"""Comment-keyword reply bot (official Meta APIs, zero subscription).

Two layers:
  Phase 1 (day 1, no App Review):
    • Scans comments on recent lead posts for the list keyword.
    • Likes the comment + replies to it with the public list link.
    • You optionally get a "pending DMs" worklist printed if DM permission
      isn't granted yet.

  Phase 2 (after one-time free App Review of instagram_manage_messages /
  instagram_manage_comments Advanced Access):
    • Actually SENDS the list by DM automatically.

Run cadence: every 30 min via .github/workflows/keyword-dm.yml, or locally:
  python scripts/reply_bot.py --list free_ai_apps
  python scripts/reply_bot.py --all
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# NOTE: heavy imports (requests, Pillow via media.lead, dotenv via core.config)
# are deferred into main() until AFTER the kill-switch check — a disabled bot
# must be instant and must never fail a CI run on a missing dependency.

# This token flavor (Facebook Login) only works on graph.facebook.com —
# graph.instagram.com rejects it with error 190. Same lesson as the publisher.
# API and SENT_LOG are bound in main() once the heavy imports succeed.


def _get(path: str, params: dict) -> dict:
    r = requests.get(f"{API}/{path}", params=params, timeout=30)
    data = r.json()
    if r.status_code >= 400:
        err = data.get("error", {})
        raise RuntimeError(f"{r.status_code} {err.get('type')}: {err.get('message')} (code {err.get('code')})")
    return data


def _post(path: str, data: dict) -> dict:
    r = requests.post(f"{API}/{path}", data={**data, "access_token": config.ACCESS_TOKEN}, timeout=30)
    payload = r.json()
    if r.status_code >= 400:
        err = payload.get("error", {})
        raise RuntimeError(f"{r.status_code} {err.get('type')}: {err.get('message')} (code {err.get('code')})")
    return payload


def find_lead_posts(hours: int = 72) -> list[dict]:
    """Recent posts whose caption contains COMMENT "<KEYWORD>"."""
    keywords = [spec["keyword"].lower() for spec in load_lists().values()]
    media = _get(
        f"{config.IG_USER_ID}/media",
        {"fields": "id,caption,timestamp,comments_count", "limit": 25, "access_token": config.ACCESS_TOKEN},
    ).get("data", [])
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).date()
    out = []
    for m in media:
        ts = (m.get("timestamp") or "")[:10]
        cap = (m.get("caption") or "").lower()
        if ts >= cutoff.isoformat() and any(f'comment "{k}"' in cap for k in keywords):
            out.append(m)
    return out


def load_sent() -> set[str]:
    if not SENT_LOG.exists():
        return set()
    with open(SENT_LOG, encoding="utf-8") as f:
        return {r["comment_id"] for r in csv.DictReader(f)}


def log_sent(comment_id: str, list_id: str, username: str, mode: str) -> None:
    new = not SENT_LOG.exists()
    with open(SENT_LOG, "a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["when", "comment_id", "list_id", "username", "mode"])
        w.writerow([datetime.utcnow().isoformat(timespec="seconds"), comment_id, list_id, username, mode])


def stack_pick() -> dict:
    """Deterministic weekly affiliate pick — every lead DM carries one."""
    products = planner.load_products()
    week = datetime.utcnow().isocalendar()[1]
    return products[week % len(products)]


def list_message(list_id: str) -> str:
    spec = load_lists()[list_id]
    lines = [f"{spec['title']} \U0001F525", ""]
    # top 6 in the DM (full list on the Lists page) — keeps links untruncated
    for it in spec["items"][:6]:
        lines.append(f"• {it['name']} - {it['desc']}\n  {it['url']}")
    lines += [
        "",
        f"...full {len(spec['items'])}-item list: link in bio -> Lists",
        "",
        f"Saved you hours? Follow {config.BRAND_HANDLE} for weekly drops.",
        "",
        "P.S. this week's stack pick:",
    ]
    p = stack_pick()
    benefit = (p.get("benefits", "").split("|")[0] or "saves hours").strip()
    trial = (p.get("trial") or "free to start").strip()
    lines += [
        f"\u2022 {p['name']} - {benefit} ({trial})",
        f"  {p['url']}",
        "(affiliate link - supports the page at no cost to you)",
    ]
    return "\n".join(lines)[:1000]


def process_comments(list_id: str, dry_run: bool = False) -> None:
    spec = load_lists()[list_id]
    keyword = spec["keyword"].lower()
    sent = load_sent()
    posts = find_lead_posts()
    if not posts:
        print(f"  no active lead posts for '{keyword}'")
        return

    for post in posts:
        comments = _get(
            f"{post['id']}/comments",
            {"fields": "id,text,username,like_count,timestamp", "limit": 50, "access_token": config.ACCESS_TOKEN},
        ).get("data", [])
        for c in comments:
            text = (c.get("text") or "").strip().lower()
            if keyword not in text or c["id"] in sent:
                continue
            username = c.get("username", "friend")
            msg = list_message(list_id)
            mode = ""
            if dry_run:
                print(f"  [dry] would serve {username}: comment {c['id']}")
                continue
            # Phase 2: send actual DM if permission exists
            try:
                _post(f"me/messages", {
                    "recipient": json.dumps({"id": c["id"]}),
                    "message": json.dumps({"text": msg}),
                })
                mode = "dm"
                print(f"  DM'd {username}")
            except RuntimeError as e:
                # Phase 1 fallback: public reply with the link
                if "code 10" in str(e) or "permission" in str(e).lower() or "10" in str(e)[:20]:
                    try:
                        _post(f"{post['id']}/comments", {"message": f"@{username} sent you the list - check your DMs! (or: link in bio -> Lists)"})
                        mode = "reply"
                        print(f"  replied publicly to {username}")
                    except RuntimeError as e2:
                        print(f"  could not serve {username}: {e2}")
                        continue
                else:
                    print(f"  could not serve {username}: {e}")
                    continue
            # engagement: like the triggering comment
            try:
                _post(f"{c['id']}/likes", {})
            except RuntimeError:
                pass
            log_sent(c["id"], list_id, username, mode)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    # Kill switch FIRST — before any heavy imports — so a disabled bot is
    # instant and can never fail a CI run on a missing dependency.
    if os.getenv("REPLY_BOT_ENABLED", "").strip().lower() not in ("1", "true", "yes"):
        print("Reply bot is switched OFF (set REPLY_BOT_ENABLED=true to activate).")
        print("Nothing was scanned or sent.")
        return

    # Heavy imports only happen when the bot is actually enabled.
    global requests, config, planner, load_lists, API, SENT_LOG
    from core.boot import setup_console
    setup_console()

    import requests  # noqa: E402

    from core import config, planner  # noqa: E402
    from media.lead import load_lists  # noqa: E402
    API = f"https://graph.facebook.com/{config.GRAPH_VERSION}"
    SENT_LOG = config.DATA_DIR / "dm_log.csv"

    available = sorted(load_lists().keys())
    if args.list and args.list not in available:
        print(f"unknown list '{args.list}' (available: {', '.join(available)})")
        return

    if not config.ACCESS_TOKEN or not config.IG_USER_ID:
        print("Credentials missing - run scripts/setup_tokens.py first.")
        print("(The bot activates itself once the token exists. Nothing else to do.)")
        return

    lists = sorted(load_lists().keys()) if args.all else ([args.list] if args.list else ["free_ai_apps"])
    for list_id in lists:
        print(f"lead bot: {list_id}")
        try:
            process_comments(list_id, dry_run=args.dry_run)
        except RuntimeError as e:
            print(f"  API error: {e}")
        time.sleep(2)


if __name__ == "__main__":
    main()
