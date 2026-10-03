"""Research-backed hook library: internet-sourced, per-product selection.

scripts/hook_research.py harvests proven hook patterns from marketing
pubs + news and distills them (Gemini) into data/hook_library.json as
TEMPLATES using only the placeholders the copy engine understands:

    {name} {benefit} {alt} {price} {trial}

This module selects the ones that fit the product's topic and the post's
concept, so copy stops sounding generic: a Pictory post gets video-pain
hooks, a Framer post gets design/portfolio hooks, and consecutive posts
don't recycle the same three lines.

Selection is deterministic per (product, concept, date) — CI runs and
local runs agree — and usage is tracked inside the library so the same
template doesn't dominate the feed. Every failure path falls back to the
built-in concept banks; a missing/rotten library never blocks posting.
"""
from __future__ import annotations

import json
import random
import re
from datetime import date
from pathlib import Path

from core import config

LIBRARY = config.DATA_DIR / "hook_library.json"

# Product topic -> keyword hits in the product row (mirrors media.stock).
_TOPIC_WORDS = {
    "design": ("design", "graphic", "figma", "portfolio", "site"),
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

# Concept id -> hook flavors that land with that angle. When the library
# tags hooks with these flavors, matching ones are preferred; without a
# match we still return hooks (variety beats perfection).
_CONCEPT_FLAVORS = {
    "stack_drop": ("proof", "numbers"),
    "before_after": ("painpoint", "transformation"),
    "honest_versus": ("curiosity", "objection"),
    "hidden_feature": ("curiosity", "mistake"),
    "price_transparency": ("objection", "numbers"),
    "mistake_angle": ("mistake", "painpoint"),
    "day_in_life": ("transformation", "painpoint"),
    "myth_crusher": ("objection", "painpoint"),
    "back_by_demand": ("proof", "curiosity"),
    "social_proof_drop": ("proof", "numbers"),
}

_PLACEHOLDERS = ("name", "benefit", "alt", "price", "trial")
_ALLOWED = set(_PLACEHOLDERS) | {"topic", "flavor"}


def _safe_format(template: str, **values: str) -> str:
    """format() with unknown placeholders left as-is instead of raising."""
    def repl(m: re.Match) -> str:
        key = m.group(1)
        return values.get(key, m.group(0))
    return re.sub(r"\{(\w+)\}", repl, template)


def load() -> dict:
    """Library dict {'updated':..., 'hooks': [...]}, or empty on any failure."""
    try:
        data = json.loads(Path(LIBRARY).read_text(encoding="utf-8"))
        hooks = data.get("hooks")
        if isinstance(hooks, list) and hooks:
            return data
    except Exception:
        pass
    return {"updated": "", "hooks": []}


def topic_for(product: dict) -> str:
    haystack = " ".join(str(product.get(k, "")).lower()
                        for k in ("name", "benefits", "specs", "id"))
    for topic, words in _TOPIC_WORDS.items():
        if any(w in haystack for w in words):
            return topic
    return "productivity"


def _hook_fields(product: dict) -> dict:
    benefits = [b for b in (product.get("benefits") or "").split("|") if b.strip()]
    benefit = (benefits[0] if benefits else "save hours every week").lower().rstrip(".")
    price = (product.get("price") or "").strip()
    currency = (product.get("currency") or "USD").strip().upper()
    if price == "0":
        price = "free"
    elif price and currency == "USD":
        price = f"${price}"
    return {
        "name": product.get("name", ""),
        "benefit": benefit,
        "alt": (product.get("alt") or "the old way").strip(),
        "price": price,
        "trial": (product.get("trial") or "free to start").strip(),
    }


def _valid(entry: dict) -> bool:
    tpl = str(entry.get("template") or "").strip()
    if not tpl or len(tpl) > 160:
        return False
    # Unknown placeholders (typos, foreign syntax) -> render junk; drop it.
    keys = set(re.findall(r"\{(\w+)\}", tpl))
    return keys <= _ALLOWED


def pick(product: dict, concept_id: str, for_date: date, rng: random.Random,
         count: int = 4, record: bool = True) -> list[str]:
    """Formatted hook strings for this product+concept, best-fit first.

    Returns [] when the library is missing/empty — callers fall back to
    their built-in concept banks, exactly as before.
    """
    hooks = [h for h in load().get("hooks", []) if isinstance(h, dict) and _valid(h)]
    if not hooks:
        return []

    topic = topic_for(product)
    flavors = _CONCEPT_FLAVORS.get(concept_id, ())

    def score(h: dict) -> tuple:
        # higher is better; tie-break deterministic via template text
        s_topic = 2 if h.get("topic") == topic else (1 if h.get("topic") in (None, "", "any") else 0)
        s_flavor = 2 if h.get("flavor") in flavors else (1 if not flavors else 0)
        used = int(h.get("uses") or 0)
        return (-s_topic, -s_flavor, used, str(h.get("template")))

    # Deterministic pre-sort, then a seeded sample from the best 60% so
    # the feed varies day to day without ever picking a poor fit.
    ranked = sorted(hooks, key=score)
    pool = ranked[: max(count, (len(ranked) * 6) // 10)]
    rng.shuffle(pool)

    fields = _hook_fields(product)
    chosen: list[str] = []
    picked: list[dict] = []
    seen_tpl: set[str] = set()
    for h in pool:
        tpl = str(h["template"]).strip()
        if tpl in seen_tpl:
            continue
        seen_tpl.add(tpl)
        chosen.append(_safe_format(tpl, **fields))
        picked.append(h)
        if len(chosen) >= count:
            break
    if picked and record:
        _bump_usage(picked)
    return chosen


def _bump_usage(picked: list[dict]) -> None:
    """Rotate popular templates out by bumping their use counts.

    Counts bump at pick time (not render time): a failed render still
    consumed the pick, and comparing formatted hooks back to templates
    would be lossy anyway. Best-effort write — a locked or malformed
    file keeps its old copy; losing a counter must never kill a run.
    """
    try:
        data = load()
        counts: dict[str, int] = {}
        for h in picked:
            tpl = str(h.get("template") or "").strip()
            counts[tpl] = counts.get(tpl, 0) + 1
        changed = False
        for h in data.get("hooks", []):
            tpl = str(h.get("template") or "").strip()
            if tpl in counts:
                h["uses"] = int(h.get("uses") or 0) + counts[tpl]
                changed = True
        if changed:
            Path(LIBRARY).write_text(json.dumps(data, indent=2, ensure_ascii=False),
                                     encoding="utf-8")
    except Exception:
        pass
