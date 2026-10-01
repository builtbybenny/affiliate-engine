"""Content concept library + freshness memory.

Concepts are ANGLES (how we present), not products (what). The planner pairs
each slot with the least-recently-featured product, then picks a concept that
hasn't been used with that product until all pairings are exhausted — then,
and only then, allows repeats. This is how the feed stays fresh forever.
"""
from __future__ import annotations

import csv
import json
from datetime import date, datetime, timedelta
from pathlib import Path

from core import config

HISTORY = config.DATA_DIR / "concept_history.json"

# Every concept carries its own hook bank. {name} = tool, {benefit}, {alt},
# {price}, {trial}. "rerun" concepts are for the repeat-exposure weave.
CONCEPTS: dict[str, dict] = {
    "stack_drop": {
        "label": "The Stack Drop",
        "desc": "Multi-tool stack carousel with prices — save + share bait",
        "formats": ["carousel"],
        "weight": 2,
        "hooks": [
            "5 tools that run my entire business (and what I pay)",
            "My {name} workflow in one stack - steal it",
            "The 5-tool stack that replaced a whole team",
        ],
    },
    "before_after": {
        "label": "Before / After",
        "desc": "Time transformation: hours -> minutes with {name}",
        "formats": ["reel"],
        "weight": 2,
        "hooks": [
            "This {name} workflow took 6 hours. Now: 20 minutes.",
            "Before {name}: chaos. After {name}: {benefit}.",
            "I fired 3 subscriptions after finding {name}",
        ],
    },
    "honest_versus": {
        "label": "Honest Versus",
        "desc": "{name} vs {alt} — fit-by-budget breakdown, no trashing",
        "formats": ["carousel"],
        "weight": 2,
        "hooks": [
            "{name} vs {alt}: the honest breakdown",
            "Stop paying for {alt} until you see this",
            "{name} or {alt}? The 5-slide answer",
        ],
    },
    "hidden_feature": {
        "label": "Hidden Feature",
        "desc": "One specific underused feature of {name} that saves hours",
        "formats": ["reel"],
        "weight": 2,
        "hooks": [
            "The {name} trick nobody tells you about",
            "90% of {name} users never find this feature",
            "Do this in {name} before your next launch",
        ],
    },
    "price_transparency": {
        "label": "Price Transparency",
        "desc": "What {name} costs vs what it replaces — honest math",
        "formats": ["carousel"],
        "weight": 1,
        "hooks": [
            "What {name} actually costs (and what it replaces)",
            "{name} pricing, honestly: {price}. The math inside.",
            "Is {name} worth it? The honest cost breakdown.",
        ],
    },
    "mistake_angle": {
        "label": "The Mistake",
        "desc": "The expensive mistake {name} prevents",
        "formats": ["reel", "carousel"],
        "weight": 1,
        "hooks": [
            "Stop losing hours to tools {name} replaces",
            "This {name} setup mistake costs you hours every week",
            "Most people use {name} wrong. Here's the fix.",
        ],
    },
    "day_in_life": {
        "label": "Day in the Life",
        "desc": "{name} slotted into a real workday timeline",
        "formats": ["reel"],
        "weight": 1,
        "hooks": [
            "A Tuesday with {name}: 9-to-5 in 15 seconds",
            "Where {name} fits in my actual workday",
            "My 9:00 uses {name}. My 14:00 needs it too.",
        ],
    },
    "myth_crusher": {
        "label": "Myth Crusher",
        "desc": "Objection demolition: '{name} is complicated/pricey'",
        "formats": ["carousel"],
        "weight": 1,
        "hooks": [
            "Myth: you need {alt}. Fact: {name} does it free.",
            "\"{name} is complicated\" - watch me set it up in 60s",
            "Myth: good tools cost a lot. Fact: {name} starts free.",
        ],
    },
    # ── Repeat-exposure concepts (honest reruns that convert scrollers) ──
    "back_by_demand": {
        "label": "Back by Demand",
        "desc": "Honest rerun: 'you asked again — here it is' with new proof",
        "formats": ["carousel", "reel"],
        "weight": 1,
        "rerun_only": True,
        "hooks": [
            "You keep asking about {name} — here it is again",
            "{name} again? Yes. Because it keeps converting.",
            "The most-requested tool this month: {name}",
        ],
    },
    "social_proof_drop": {
        "label": "Social Proof Drop",
        "desc": "'X people grabbed this last week' momentum post",
        "formats": ["reel", "carousel"],
        "weight": 1,
        "rerun_only": True,
        "hooks": [
            "Hundreds grabbed {name}'s free trial last week",
            "{name} keeps selling itself. Look at the DMs.",
            "Still thinking about {name}? 200+ started free last week.",
        ],
    },
}


def load_history() -> dict:
    if HISTORY.exists():
        return json.loads(HISTORY.read_text(encoding="utf-8"))
    return {"pairings": [], "product_last": {}}


def save_history(h: dict) -> None:
    HISTORY.write_text(json.dumps(h, indent=2), encoding="utf-8")


def _pair_key(concept: str, product_id: str) -> str:
    return f"{concept}::{product_id}"


def pick_concept(product: dict, format_name: str, for_date: date, rng,
                 min_repeat_days: int = 21, record: bool = True) -> tuple[str, bool]:
    """Pick a concept for this product+format. Returns (concept_id, is_rerun).

    record=False for dry-runs: decide without mutating history.

    Rules:
      • concept's formats must include format_name
      • prefer pairings never used; if all used, allow oldest-used one
        (naturally cycles without repetition until exhaustion)
      • if product was featured within min_repeat_days, MUST use a rerun
        concept (honest framing) instead of pretending it's new
    """
    h = load_history()
    pid = product.get("id") or product["name"]
    eligible = [cid for cid, c in CONCEPTS.items() if format_name in c["formats"]]

    # Repeat-exposure detection: product featured recently?
    last_iso = h.get("product_last", {}).get(pid)
    recently_featured = False
    if last_iso:
        last = date.fromisoformat(last_iso)
        if (for_date - last).days < min_repeat_days:
            recently_featured = True

    rerun_pool = [c for c in eligible if CONCEPTS[c].get("rerun_only")]
    fresh_pool = [c for c in eligible if not CONCEPTS[c].get("rerun_only")]

    pairings = set(h.get("pairings", []))

    if recently_featured:
        # Honest rerun: pick the least-recently-used rerun concept for this product
        candidates = []
        for cid in rerun_pool:
            count = sum(1 for p in pairings if p.startswith(cid + "::" + pid))
            candidates.append((count, cid))
        candidates.sort()
        cid = candidates[0][1] if candidates else rng.choice(eligible)
        if record:
            _record(h, cid, pid, for_date)
        return cid, True

    # Fresh concepts first: unused pairings
    unused = [c for c in fresh_pool if _pair_key(c, pid) not in pairings]
    if unused:
        # weight by concept weight
        weighted = []
        for c in unused:
            weighted += [c] * CONCEPTS[c]["weight"]
        cid = rng.choice(weighted)
        if record:
            _record(h, cid, pid, for_date)
        return cid, False

    # All fresh pairings exhausted for this product+format: recycle oldest
    used = [c for c in fresh_pool if _pair_key(c, pid) in pairings]
    if used:
        cid = rng.choice(used)
        if record:
            _record(h, cid, pid, for_date)
        return cid, False

    cid = rng.choice(eligible)
    if record:
        _record(h, cid, pid, for_date)
    return cid, False


def _record(h: dict, concept: str, pid: str, for_date: date) -> None:
    h.setdefault("pairings", []).append(_pair_key(concept, pid))
    # keep history bounded
    h["pairings"] = h["pairings"][-500:]
    h.setdefault("product_last", {})[pid] = for_date.isoformat()
    save_history(h)
