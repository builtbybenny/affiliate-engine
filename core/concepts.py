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
    # ── Journey-gap concepts (added 2026-10-25 content rebuild) ────────
    # Every post now names ONE gap in the viewer's journey and shows this
    # tool closing it. The two fake-demand concepts that used to live here
    # ("You keep asking about {name} — here it is again" / "200+ started
    # free last week") were DELETED: a 0-follower page has nobody asking and
    # the numbers were invented — they also ate every slot because
    # pick_concept forced a rerun concept whenever a product had posted in
    # the last 21 days, which with a small catalog is always.
    "cost_of_waiting": {
        "label": "The Cost of Waiting",
        "desc": "What the gap costs them every week it stays open",
        "formats": ["reel", "carousel"],
        "weight": 2,
        "journey": "pain made expensive — quantify what doing nothing costs "
                   "per week/month, then close it with the tool's first step",
        "hooks": [
            "Every week without this costs you {benefit}",
            "The {alt} habit costs more than {name} does",
            "You pay for the slow way every single week",
        ],
    },
    "quick_win": {
        "label": "The Quick Win",
        "desc": "One result they can have today, tool as the enabler",
        "formats": ["reel", "carousel"],
        "weight": 2,
        "journey": "activation — one concrete outcome achievable in minutes, "
                   "so the click feels like the shortest path to it",
        "hooks": [
            "Fix this in 10 minutes, before your next launch",
            "One setting in {name} changes your whole week",
            "The fastest first win with {name} ({trial})",
        ],
    },
    "objection_crusher": {
        "label": "Objection Crusher",
        "desc": "The real blocker (price / time / skill) answered plainly",
        "formats": ["reel", "carousel"],
        "weight": 2,
        "journey": "objection stage — name the exact reason they are not "
                   "signing up, answer it with a fact, then ask for the click",
        "hooks": [
            "The reason you skip tools like {name} is wrong",
            "{name} costs {price} — here is what that replaces",
            "'I do not have time to learn it' — {trial} says try first",
        ],
    },
    "workflow_gap": {
        "label": "The Missing Step",
        "desc": "The step between what they already do and the result",
        "formats": ["reel", "carousel"],
        "weight": 1,
        "journey": "awareness of the gap — they already do most of the work; "
                   "show the one missing step and that {name} is it",
        "hooks": [
            "You are one step short of {benefit}",
            "The step everyone skips after launching",
            "What happens between the idea and {benefit}",
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
      • prefer pairings never used; when everything has been used, recycle the
        LEAST-recently-used pairing (natural cycling, no frozen repeat)
      • never pick the same concept twice in a row for the same product

    2026-10-25: the old "recently featured -> MUST use a rerun concept" rule
    is gone. With a small catalog at 1-2 posts/day every product is 'recently
    featured' every time, so it forced one of the two rerun concepts on ~100%
    of posts — that is exactly why the feed kept shipping "You keep asking
    about X — here it is again" / "The most-requested tool this month".
    Both rerun concepts were deleted with it. is_rerun stays in the return
    signature (callers print it) and is now always False.
    """
    h = load_history()
    pid = product.get("id") or product["name"]
    eligible = [cid for cid, c in CONCEPTS.items() if format_name in c["formats"]]
    if not eligible:
        raise ValueError(f"no concepts support format {format_name!r}")

    pairings = set(h.get("pairings", []))
    concept_last: dict[str, str] = h.get("concept_last", {})

    # Unused pairings first, weighted by concept weight.
    unused = [c for c in eligible if _pair_key(c, pid) not in pairings]
    if unused:
        weighted: list[str] = []
        for c in unused:
            weighted += [c] * CONCEPTS[c]["weight"]
        cid = rng.choice(weighted)
        if record:
            _record(h, cid, pid, for_date)
        return cid, False

    # Everything paired already: least-recently-used first, never the one we
    # used for this product's previous post.
    def _last(cid: str) -> str:
        return concept_last.get(_pair_key(cid, pid), "")

    used = [c for c in eligible if _pair_key(c, pid) in pairings]
    order = sorted(used, key=_last)
    # Skip the concept used most recently for THIS product when an alternative
    # exists (two products x eight angles means we always have one).
    recent = order[-1] if order else ""
    pool = [c for c in order if c != recent] or order
    cid = rng.choice(pool)
    if record:
        _record(h, cid, pid, for_date)
    return cid, False


def _record(h: dict, concept: str, pid: str, for_date: date) -> None:
    h.setdefault("pairings", []).append(_pair_key(concept, pid))
    # keep history bounded
    h["pairings"] = h["pairings"][-500:]
    h.setdefault("product_last", {})[pid] = for_date.isoformat()
    # recency per concept+product, so recycling is least-recently-used instead
    # of random (a random recycle repeats visibly with only ~8 angles in play)
    cl = h.setdefault("concept_last", {})
    cl[_pair_key(concept, pid)] = for_date.isoformat()
    if len(cl) > 400:
        for k in sorted(cl, key=lambda k: cl[k])[: len(cl) - 400]:
            cl.pop(k, None)
    save_history(h)
