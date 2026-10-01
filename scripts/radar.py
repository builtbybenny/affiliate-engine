#!/usr/bin/env python3
"""Trend radar: continuous market exposure from FREE sources.

Pulls RSS feeds (Product Hunt, TechCrunch, VentureBeat AI, HN front page),
detects SaaS/tool launches, scores them against our niche, and:
  • maintains data/radar_candidates.json (rolling, deduped)
  • writes data/radar_digest_YYYY-Www.md (weekly human-readable digest)

Run locally:  python scripts/radar.py
Automated:    .github/workflows/weekly-evolve.yml (Sundays)
Zero dependencies: stdlib xml.etree + urllib.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console  # noqa: E402

setup_console()

from core import config  # noqa: E402

CANDIDATES = config.DATA_DIR / "radar_candidates.json"

FEEDS = {
    "producthunt": "https://www.producthunt.com/feed",
    "techcrunch": "https://techcrunch.com/category/apps/feed/",
    "venturebeat-ai": "https://venturebeat.com/category/ai/feed/",
    "hn-front": "https://hnrss.org/frontpage",
}

# words that make an item promotable as a SaaS affiliate pick
SIGNALS = {
    "ai": 3, "app": 2, "tool": 2, "launch": 2, "beta": 1, "free": 3,
    "startup": 1, "saas": 3, "automation": 2, "no-code": 2, "nocode": 2,
    "productivity": 2, "crm": 2, "email": 1, "design": 1, "video": 1,
    "writing": 1, "agents": 2, "dashboard": 1, "analytics": 2, "api": 1,
    "template": 1, "workspace": 2, "notes": 1, "forms": 1, "copilot": 2,
}
NOISE = {
    "crypto", "nft", "bitcoin", "election", "sports", "celebrity",
    "movie", "tv show", "lawsuit", "ipo", "earnings", "layoffs",
}


def fetch(url: str, timeout: int = 20) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "StackAndSave-Radar/1.0"})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def parse_feed(xml_bytes: bytes) -> list[dict]:
    items: list[dict] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return items
    for el in root.iter("item"):
        title = (el.findtext("title") or "").strip()
        link = (el.findtext("link") or "").strip()
        desc = re.sub(r"<[^>]+>", "", el.findtext("description") or "").strip()
        pub = (el.findtext("pubDate") or "").strip()
        if title:
            items.append({"title": title, "link": link, "desc": desc[:280], "date": pub})
    # Atom fallback
    if not items:
        ns = {"a": "http://www.w3.org/2005/Atom"}
        for el in root.findall("a:entry", ns):
            title = (el.findtext("a:title", namespaces=ns) or "").strip()
            link_el = el.find("a:link", ns)
            link = link_el.get("href") if link_el is not None else ""
            desc = re.sub(r"<[^>]+>", "", el.findtext("a:summary", namespaces=ns) or "").strip()
            if title:
                items.append({"title": title, "link": link, "desc": desc[:280], "date": ""})
    return items


def score(item: dict) -> int:
    text = (item["title"] + " " + item["desc"]).lower()
    if any(n in text for n in NOISE):
        return 0
    return sum(v for k, v in SIGNALS.items() if k in text)


def load_candidates() -> dict:
    if CANDIDATES.exists():
        try:
            return json.loads(CANDIDATES.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"items": {}, "last_run": ""}


def main() -> None:
    db = load_candidates()
    cutoff = datetime.now(timezone.utc) - timedelta(days=14)
    new_count = 0

    for feed_name, url in FEEDS.items():
        xml = fetch(url)
        if not xml:
            print(f"  [{feed_name}] fetch failed (skipping)")
            continue
        for item in parse_feed(xml):
            s = score(item)
            if s < 4:
                continue
            key = re.sub(r"\W+", "", item["title"].lower())[:80]
            if not key or key in db["items"]:
                continue
            db["items"][key] = {
                "title": item["title"][:120],
                "link": item["link"],
                "desc": item["desc"],
                "score": s,
                "source": feed_name,
                "seen": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            new_count += 1

    # prune old / keep top 100 by score
    for key, it in list(db["items"].items()):
        seen = datetime.fromisoformat(it["seen"])
        if seen < cutoff:
            del db["items"][key]
    top = dict(sorted(db["items"].items(), key=lambda kv: -kv[1]["score"])[:100])
    db["items"] = top
    db["last_run"] = datetime.now(timezone.utc).isoformat(timespec="seconds")

    CANDIDATES.write_text(json.dumps(db, indent=2), encoding="utf-8")
    print(f"radar: {new_count} new candidates, {len(db['items'])} tracked")

    # ── weekly digest ─────────────────────────────────────────────────
    week = datetime.now(timezone.utc).strftime("%G-W%V")
    digest = config.DATA_DIR / f"radar_digest_{week}.md"
    lines = [
        f"# Radar digest {week}",
        "",
        f"Auto-generated {db['last_run'][:10]} from "
        + ", ".join(FEEDS.keys())
        + ". Ranked by promotability score.",
        "",
        "| Score | Tool/story | Why it matters | Source |",
        "|---|---|---|---|",
    ]
    for it in sorted(top.values(), key=lambda i: -i["score"])[:25]:
        lines.append(
            f"| {it['score']} | [{it['title'][:60]}]({it['link'][:80]}) "
            f"| {it['desc'][:80]} | {it['source']} |"
        )
    lines += [
        "",
        "## Sunday ritual (5 min)",
        "1. Skim the top 10. Pick 1-2 tools worth promoting.",
        "2. Check they have a free trial + affiliate/partner program.",
        "3. Add to data/products.csv with your referral link.",
        "4. The engine takes over: concepts, renders, posting, logging.",
        "5. Prune dead products from products.csv while you're there.",
    ]
    digest.write_text("\n".join(lines), encoding="utf-8")
    print(f"digest: {digest}")


if __name__ == "__main__":
    main()
