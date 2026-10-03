#!/usr/bin/env python3
"""Hook research: harvest proven hooks from the internet, distill to templates.

Pipeline (free sources only, no API keys beyond the Gemini key we have):

  1. HARVEST  — pull RSS from copywriting/marketing pubs + Google News
                queries ("hooks that convert", "instagram hooks", ...).
                Raw material = real headlines that already earned clicks.
  2. DISTILL  — Gemini turns them into hook TEMPLATES using only our
                placeholders ({name} {benefit} {alt} {price} {trial}),
                each tagged with a topic + flavor (painpoint/curiosity/
                mistake/objection/transformation/proof/numbers) so
                core/hooklib.py can match them per product + concept.
  3. MERGE    — dedupe into data/hook_library.json (cap 300, usage counts
                preserved), so the pool only grows and never repeats junk.

Run locally:  python scripts/hook_research.py
Automated:    .github/workflows/weekly-evolve.yml (Sundays)
Failure mode: keeps the existing library untouched and exits 0 — the
              posting pipeline never depends on this succeeding.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console  # noqa: E402

setup_console()

from core import config, llm  # noqa: E402

LIBRARY = config.DATA_DIR / "hook_library.json"
HISTORY = config.DATA_DIR / "hook_research_log.json"
MAX_HOOKS = 300
UA = "StackAndSave-HookResearch/1.0"

# Copywriting/marketing pubs whose headlines ARE the raw material.
FEEDS = {
    "copyblogger": "https://copyblogger.com/feed/",
    "problogger": "https://feeds.feedburner.com/ProBlogger",
    "cmi": "https://contentmarketinginstitute.com/feed/",
    "marketingweek": "https://marketingweek.com/feed/",
    "ahrefs": "https://ahrefs.com/blog/feed/",
}

# Google News RSS queries — high-volume click-proven phrasing.
NEWS_QUERIES = [
    "hooks that convert social media",
    "instagram hooks stop scrolling",
    "headline formulas copywriting",
    "viral video hooks marketing",
    "pain point marketing examples",
]

ALLOWED_PLACEHOLDERS = {"name", "benefit", "alt", "price", "trial"}
TOPICS = {"design", "video", "email", "website", "sell", "course",
          "social", "automation", "ai", "productivity"}
FLAVORS = {"painpoint", "curiosity", "mistake", "objection",
           "transformation", "proof", "numbers"}


def fetch(url: str, timeout: int = 20) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except Exception:
        return None


def feed_titles(xml_bytes: bytes) -> list[str]:
    """Titles from an RSS/Atom feed. Titles = ready-made hook samples."""
    out: list[str] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return out
    for el in root.iter("item"):
        t = (el.findtext("title") or "").strip()
        if t:
            out.append(re.sub(r"\s+", " ", t)[:200])
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for el in root.findall("a:entry", ns):
        t = (el.findtext("a:title", namespaces=ns) or "").strip()
        if t:
            out.append(re.sub(r"\s+", " ", t)[:200])
    return out


def harvest() -> list[dict]:
    """All raw headlines with their source, deduped."""
    raw: dict[str, str] = {}
    for name, url in FEEDS.items():
        xml = fetch(url)
        if not xml:
            print(f"  [{name}] fetch failed (skipping)")
            continue
        n = 0
        for t in feed_titles(xml):
            key = re.sub(r"\W+", "", t.lower())[:80]
            if key and key not in raw:
                raw[key] = t
                n += 1
        print(f"  [{name}] {n} titles")
    for q in NEWS_QUERIES:
        url = ("https://news.google.com/rss/search?q="
               + urllib.parse.quote(q) + "&hl=en-US&gl=US&ceid=US:en")
        xml = fetch(url)
        if not xml:
            print(f"  [news:{q[:24]}] fetch failed (skipping)")
            continue
        n = 0
        for t in feed_titles(xml):
            key = re.sub(r"\W+", "", t.lower())[:80]
            if key and key not in raw:
                raw[key] = t
                n += 1
        print(f"  [news:{q[:24]}] {n} titles")
    return [{"headline": t} for t in raw.values()]


DISTILL_PROMPT = """You are a direct-response social copywriter for 'Stack & Save', \
a faceless page that promotes SaaS tools via affiliate free-trial links.

Below are real headlines harvested from marketing publications and news. \
They earned clicks — extract the UNDERLYING hook patterns, not the literal topics.

Return STRICT JSON: {"hooks": [ ... ]} with 40-60 entries. Each entry:
  "template": a hook sentence for an Instagram/Facebook post promoting a tool.
      Use ONLY these placeholders: {name} (the tool), {benefit} (its first
      benefit), {alt} (competitor/old way), {price} (price or 'free'),
      {trial} (free-trial wording). No other braces. Max 15 words.
  "topic": one of design, video, email, website, sell, course, social,
      automation, ai, productivity — which tool category it fits best.
  "flavor": one of painpoint, curiosity, mistake, objection,
      transformation, proof, numbers.
  "why": <=10 words on why this hook converts.

Rules:
- Pain-point hooks must name a recognizable daily frustration (no jargon).
- Non-pain hooks: curiosity, proof, numbers, objection-handling — vary them.
- Scroller-first: never open with a tool name or 'introducing'.
- US spelling. No emojis in templates. No income claims. No hype words
  like 'game-changer', 'unlock', 'revolutionary'.
- At least 12 distinct templates must use {name} naturally.
- Cover ALL ten topics and ALL seven flavors roughly evenly.

HARVESTED HEADLINES (raw material):
{headlines}
"""


def distill(headlines: list[str]) -> list[dict] | None:
    if not llm.available():
        print("  no GEMINI_API_KEY — cannot distill (keeping old library)")
        return None
    # NOTE: the prompt contains literal {name}/{benefit} placeholders the
    # model must see — plain replace(), not str.format(), would mangle them.
    prompt = DISTILL_PROMPT.replace(
        "{headlines}", "\n".join(f"- {h}" for h in headlines)
    )
    raw = llm._generate(prompt, max_tokens=4000)
    if not raw:
        print("  Gemini returned nothing (keeping old library)")
        return None
    try:
        data = json.loads(raw)
        hooks = data.get("hooks") if isinstance(data, dict) else data
        if not isinstance(hooks, list):
            raise ValueError("no list")
    except Exception as e:
        print(f"  distill parse failed: {e!r} (keeping old library)")
        return None

    clean: list[dict] = []
    for h in hooks:
        if not isinstance(h, dict):
            continue
        tpl = re.sub(r"\s+", " ", str(h.get("template") or "")).strip()
        topic = str(h.get("topic") or "").strip().lower()
        flavor = str(h.get("flavor") or "").strip().lower()
        if not tpl or len(tpl) > 160:
            continue
        if topic not in TOPICS or flavor not in FLAVORS:
            continue
        keys = set(re.findall(r"\{(\w+)\}", tpl))
        if not keys <= ALLOWED_PLACEHOLDERS:
            continue
        clean.append({
            "template": tpl,
            "topic": topic,
            "flavor": flavor,
            "why": str(h.get("why") or "")[:80],
            "uses": 0,
            "source": "research",
            "added": datetime.now(timezone.utc).date().isoformat(),
        })
    print(f"  distilled {len(clean)} valid templates from {len(hooks)} candidates")
    return clean or None


def merge(fresh: list[dict]) -> tuple[int, int]:
    """Merge into the library; keep usage counts; cap size. Returns (added, total)."""
    old = {"updated": "", "hooks": []}
    if LIBRARY.exists():
        try:
            loaded = json.loads(LIBRARY.read_text(encoding="utf-8"))
            if isinstance(loaded.get("hooks"), list):
                old = loaded
        except Exception:
            pass
    index = {str(h.get("template", "")).strip().lower(): h
             for h in old["hooks"] if isinstance(h, dict)}
    added = 0
    for h in fresh:
        key = h["template"].strip().lower()
        if key not in index:
            index[key] = h
            added += 1
    hooks = list(index.values())
    if len(hooks) > MAX_HOOKS:
        # Keep the freshest, but never drop anything in active rotation.
        hooks.sort(key=lambda h: (str(h.get("added", "")), int(h.get("uses") or 0)),
                   reverse=True)
        hooks = hooks[:MAX_HOOKS]
    old["hooks"] = hooks
    old["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    LIBRARY.write_text(json.dumps(old, indent=2, ensure_ascii=False), encoding="utf-8")
    return added, len(hooks)


def main() -> None:
    print("hook research: harvest -> distill -> merge")
    harvested = harvest()
    print(f"  harvested {len(harvested)} unique headlines total")
    if not harvested:
        print("  nothing harvested (network?) — keeping old library")
        return
    # Cap the prompt: newest ~120 headlines is plenty of raw material.
    headlines = [h["headline"] for h in harvested][:120]
    fresh = distill(headlines)
    if not fresh:
        return
    added, total = merge(fresh)
    try:
        log = {}
        if HISTORY.exists():
            try:
                log = json.loads(HISTORY.read_text(encoding="utf-8"))
            except Exception:
                log = {}
        log[datetime.now(timezone.utc).date().isoformat()] = {
            "harvested": len(harvested), "distilled": len(fresh), "added": added,
        }
        HISTORY.write_text(json.dumps(log, indent=2), encoding="utf-8")
    except Exception:
        pass
    print(f"library: +{added} new, {total} total")


if __name__ == "__main__":
    main()
