"""Per-product research briefs: real blog facts + search keywords for captions.

Replaces the static hook bank (data/hook_library.json, dumped 2026-10-05).
Instead of recycling template hooks, every post gets copy grounded in what
the internet actually says about the tool:

  1. HARVEST — Google News RSS for "<tool> review / pricing / alternative"
               + article text from marketing/SaaS blogs (feeds below).
  2. DISTILL — Gemini turns the excerpts into a brief: search keywords
               people actually use, attributable facts/stats, buyer
               objections in their own words, and pain-led hook angles.
  3. CACHE   — data/research_briefs.json keyed by product id, refreshed
               when older than MAX_AGE_DAYS (weekly in CI via
               scripts/research_brief.py, lazily at generate time).

Every failure path falls back: stale brief -> empty brief -> the post
still renders with product data alone. The posting pipeline never blocks
on a fetch or on Gemini.
"""
from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

from core import config, llm

BRIEFS = config.DATA_DIR / "research_briefs.json"
MAX_AGE_DAYS = 7
UA = "StackAndSave-Research/1.0"

# Marketing/SaaS blogs whose articles are fetchable plain HTML.
FEEDS = {
    "copyblogger": "https://copyblogger.com/feed/",
    "problogger": "https://feeds.feedburner.com/ProBlogger",
    "cmi": "https://contentmarketinginstitute.com/feed/",
    "ahrefs": "https://ahrefs.com/blog/feed/",
    "hubspot": "https://blog.hubspot.com/marketing/rss",
}

# Product-row keywords -> the category vocabulary buyers search with.
_TOPIC_WORDS = {
    "design": ("design", "graphic", "figma", "portfolio", "site", "landing"),
    "video": ("video", "film", "reel", "edit", "clip", "caption"),
    "email": ("email", "mail", "newsletter", "audience"),
    "website": ("website", "builder", "landing", "host", "web", "page"),
    "sell": ("sell", "store", "ecommerce", "cart", "shop", "funnel", "crm"),
    "course": ("course", "teach", "academy", "learn", "webinar"),
    "social": ("social", "instagram", "schedule", "post", "content"),
    "automation": ("automat", "workflow", "zap", "integrat", "agency"),
    "ai": ("ai", "gpt", "assistant", "bot", "caption"),
    "productivity": ("note", "task", "project", "team", "workspace"),
}


def _topic_of(product: dict) -> str:
    haystack = " ".join(str(product.get(k, "")).lower()
                        for k in ("name", "benefits", "specs", "id"))
    for topic, words in _TOPIC_WORDS.items():
        if any(w in haystack for w in words):
            return topic
    return "productivity"


def _fetch(url: str, timeout: int = 12) -> bytes | None:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()[:400_000]
    except Exception:
        return None


def _feed_items(xml_bytes: bytes) -> list[tuple[str, str]]:
    """(title, link) pairs from an RSS/Atom feed."""
    out: list[tuple[str, str]] = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return out
    for el in root.iter("item"):
        t = (el.findtext("title") or "").strip()
        link = (el.findtext("link") or "").strip()
        if t:
            out.append((re.sub(r"\s+", " ", t)[:200], link))
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for el in root.findall("a:entry", ns):
        t = (el.findtext("a:title", namespaces=ns) or "").strip()
        link_el = el.find("a:link", ns)
        link = (link_el.get("href") or "") if link_el is not None else ""
        if t:
            out.append((re.sub(r"\s+", " ", t)[:200], link))
    return out


def _article_text(url: str, limit: int = 3500) -> str:
    """Readable paragraphs from an article page (script/style stripped)."""
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.skip = 0
            self.parts: list[str] = []

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style", "nav", "header", "footer", "aside"):
                self.skip += 1

        def handle_endtag(self, tag):
            if tag in ("script", "style", "nav", "header", "footer", "aside"):
                self.skip = max(0, self.skip - 1)

        def handle_data(self, data):
            if not self.skip:
                text = data.strip()
                if len(text) > 40:  # paragraphs, not menu labels
                    self.parts.append(text)

    raw = _fetch(url)
    if not raw:
        return ""
    html = raw.decode("utf-8", errors="ignore")
    p = _P()
    try:
        p.feed(html)
    except Exception:
        return ""
    return " ".join(p.parts)[:limit]


def _news_titles(product: dict, topic: str) -> list[str]:
    """Headline signals for what the internet says about this tool right now."""
    name = product.get("name", "")
    alt = (product.get("alt") or "").strip()
    queries = [
        f'"{name}" review',
        f'"{name}" pricing OR plan',
        f"{name} vs {alt}" if alt and alt != "the old way" else f"{name} tips",
        f"{topic} tools statistics",
    ]
    titles: list[str] = []
    for q in queries:
        url = ("https://news.google.com/rss/search?q="
               + urllib.parse.quote(q) + "&hl=en-US&gl=US&ceid=US:en")
        xml = _fetch(url)
        if not xml:
            continue
        for t, _ in _feed_items(xml)[:8]:
            if t not in titles:
                titles.append(t)
    return titles[:24]


def _blog_articles(product: dict, topic: str, want: int = 5) -> list[str]:
    """Fetch article bodies from marketing blogs; prefer topic-relevant titles."""
    name_words = {w.lower() for w in re.findall(r"\w+", str(product.get("name", "")))}
    topic_words = set(_TOPIC_WORDS.get(topic, ()))
    relevant: list[str] = []
    general: list[str] = []
    seen: set[str] = set()
    for feed in FEEDS.values():
        if len(relevant) >= want:
            break
        xml = _fetch(feed)
        if not xml:
            continue
        for title, link in _feed_items(xml):
            if not link.startswith("http") or len(relevant) + len(general) >= want * 2:
                continue
            if title[:40] in seen:
                continue
            seen.add(title)
            low = title.lower()
            hit = (bool(name_words & set(re.findall(r"\w+", low)))
                   or any(w in low for w in topic_words))
            text = _article_text(link)
            if not text:
                continue
            entry = f"[{title}] {text}"
            (relevant if hit else general).append(entry)
    return (relevant + general)[:want]


DISTILL_PROMPT = """You are the research desk for 'Stack & Save', a faceless Instagram \
page that promotes SaaS tools via affiliate free-trial links. Today's post is about \
{topic} tool: {name} (does: {benefits}; price: {price} {currency}; vs: {alt}).

Below are (a) recent news headlines mentioning it and (b) excerpts from marketing \
blogs. They are raw research material for an Instagram caption that must be specific, \
attributable, and searchable.

Return STRICT JSON with EXACTLY these keys:
  "keywords": 5-8 short lowercase search phrases real people type when looking for \
this kind of tool (mix category phrases like "best email newsletter tools" and \
problem phrases like "send newsletters for free") — these become caption SEO keywords.
  "facts": 4-8 one-line facts or statistics DIRECTLY supported by the HEADLINES or \
ARTICLE EXCERPTS below, each ending with (source: <the publication/site named in \
that excerpt>). If fewer than 4 real ones exist, return fewer. NEVER invent a \
number and NEVER write a generic source like 'research desk'.
  "objections": 2-4 honest buyer doubts in the buyer's own words (e.g. "will I lose \
my subscribers if I switch").
  "angles": 4-6 scroll-stopping hook statements for THIS tool — declarations under \
10 words with a number or concrete cost where possible. Pain/problem first, never \
a question, never opening with the tool name.

US spelling. Plain words a non-tech person gets. No hype words (supercharge, \
unlock, game-changing, seamless). JSON only.

HEADLINES:
{headlines}

ARTICLE EXCERPTS:
{articles}
"""


def _distill(product: dict, topic: str, headlines: list[str], articles: list[str]) -> dict | None:
    if not llm.available():
        return None
    prompt = (
        DISTILL_PROMPT
        .replace("{topic}", topic)
        .replace("{name}", str(product.get("name", "")))
        .replace("{benefits}", str(product.get("benefits", ""))[:200])
        .replace("{price}", str(product.get("price", "")))
        .replace("{currency}", str(product.get("currency", "")))
        .replace("{alt}", str(product.get("alt", "")))
        .replace("{headlines}", "\n".join(f"- {h}" for h in headlines) or "(none)")
        .replace("{articles}", "\n\n".join(articles)[:14000] or "(none)")
    )
    raw = llm._generate(prompt, max_tokens=3000)
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except Exception:
        return None
    brief = {
        "keywords": [str(k).strip().lower() for k in data.get("keywords", []) if str(k).strip()][:8],
        "facts": [str(f).strip() for f in data.get("facts", []) if str(f).strip()][:8],
        "objections": [str(o).strip() for o in data.get("objections", []) if str(o).strip()][:4],
        "angles": [str(a).strip() for a in data.get("angles", []) if str(a).strip()][:6],
    }
    return brief if brief["keywords"] and brief["angles"] else None


def _load() -> dict:
    try:
        data = json.loads(BRIEFS.read_text(encoding="utf-8"))
        if isinstance(data.get("products"), dict):
            return data
    except Exception:
        pass
    return {"updated": "", "products": {}}


def _save(data: dict) -> None:
    try:
        BRIEFS.parent.mkdir(parents=True, exist_ok=True)
        BRIEFS.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    except Exception:
        pass


def build(product: dict) -> dict | None:
    """Harvest + distill a fresh brief for this product (network required)."""
    topic = _topic_of(product)
    headlines = _news_titles(product, topic)
    articles = _blog_articles(product, topic)
    if not headlines and not articles:
        return None
    brief = _distill(product, topic, headlines, articles)
    if brief:
        brief["built"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        brief["sources"] = {"headlines": len(headlines), "articles": len(articles)}
    return brief


def get(product: dict, refresh: bool = True, max_age_days: int = MAX_AGE_DAYS) -> dict:
    """Cached brief for this product; rebuilds when stale (best-effort).

    Always returns a dict — {} means no research available, and callers
    fall back to product-data copy.
    """
    pid = str(product.get("id") or product.get("name") or "").lower()
    data = _load()
    entry = data["products"].get(pid) or {}
    if entry:
        try:
            built = datetime.fromisoformat(str(entry.get("built", "")))
            age = (datetime.now(timezone.utc) - built).days
            if age < max_age_days:
                return dict(entry, stale=False)
        except Exception:
            pass
    if refresh:
        fresh = build(product)
        if fresh:
            data = _load()
            data["products"][pid] = fresh
            data["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
            _save(data)
            return dict(fresh, stale=False)
    # network/Gemini failed — serve the stale brief rather than nothing
    return dict(entry, stale=True) if entry else {}


def status() -> tuple[int, str]:
    """(product briefs on disk, last update iso) for doctor.py."""
    data = _load()
    return len(data["products"]), str(data.get("updated", ""))


def refresh_all(products: list[dict]) -> None:
    """Rebuild every product's brief (weekly CI / scripts/research_brief.py)."""
    data = _load()
    for p in products:
        pid = str(p.get("id") or p.get("name") or "").lower()
        print(f"  [{pid}] ", end="", flush=True)
        fresh = build(p)
        if fresh:
            data["products"][pid] = fresh
            print(f"keywords={len(fresh['keywords'])} facts={len(fresh['facts'])} "
                  f"angles={len(fresh['angles'])}")
        else:
            print("failed (kept old)")
    data["updated"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _save(data)
