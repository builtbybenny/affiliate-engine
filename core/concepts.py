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

# Concepts choose an editorial lens. Hooks are generated from the product row
# at runtime so new products inherit the same evidence and quality rules.
CONCEPTS: dict[str, dict] = {
    "stack_drop": {
        "label": "The Stack Lens",
        "desc": "A focused look at the featured product's listed capabilities",
        "formats": ["carousel"],
        "weight": 2,
    },
    "before_after": {
        "label": "Workflow Fit",
        "desc": "Connect a reader's workflow to listed product capabilities",
        "formats": ["reel"],
        "weight": 2,
    },
    "honest_versus": {
        "label": "Plan Comparison",
        "desc": "Check plan fit using current terms and listed capabilities",
        "formats": ["carousel"],
        "weight": 2,
    },
    "hidden_feature": {
        "label": "Product Detail",
        "desc": "Explain one listed capability without inventing outcomes",
        "formats": ["reel"],
        "weight": 2,
    },
    "price_transparency": {
        "label": "Price Transparency",
        "desc": "Review listed price and terms without inventing savings",
        "formats": ["carousel"],
        "weight": 1,
    },
    "mistake_angle": {
        "label": "Decision Check",
        "desc": "A decision point answered with verified product details",
        "formats": ["reel", "carousel"],
        "weight": 1,
    },
    "day_in_life": {
        "label": "Workflow Context",
        "desc": "A realistic workflow scenario without claiming personal experience",
        "formats": ["reel"],
        "weight": 1,
    },
    "myth_crusher": {
        "label": "Objection Check",
        "desc": "Answer an objection only when listed facts support it",
        "formats": ["carousel"],
        "weight": 1,
    },
    # ── Journey-gap concepts (added 2026-10-25 content rebuild) ────────
    # Every post chooses ONE relevant reader decision or gap. Quantify a cost
    # or outcome only when the product row supplies evidence. The two fake-
    # demand concepts that used to live here
    # ("You keep asking about {name} — here it is again" / "200+ started
    # free last week") were DELETED: a 0-follower page has nobody asking and
    # the numbers were invented — they also ate every slot because
    # pick_concept forced a rerun concept whenever a product had posted in
    # the last 21 days, which with a small catalog is always.
    "cost_of_waiting": {
        "label": "Cost or Trade-off",
        "desc": "Describe a real trade-off; quantify only when evidence is supplied",
        "formats": ["reel", "carousel"],
        "weight": 2,
        "journey": "decision stage — name a cost only when the product data "
                   "supports it; otherwise describe the trade-off without numbers",
    },
    "quick_win": {
        "label": "Quick Start",
        "desc": "One clear next step based on a listed product capability",
        "formats": ["reel", "carousel"],
        "weight": 2,
        "journey": "activation — identify a useful next step tied to a listed "
                   "capability; do not promise a speed or outcome the data omits",
    },
    "objection_crusher": {
        "label": "Objection Response",
        "desc": "Address one blocker only when the product row supports an answer",
        "formats": ["reel", "carousel"],
        "weight": 2,
        "journey": "objection stage — answer only with a matching catalog fact; "
                   "if the row does not support an answer, do not invent one",
    },
    "workflow_gap": {
        "label": "Workflow Step",
        "desc": "A possible next step, grounded in a listed product capability",
        "formats": ["reel", "carousel"],
        "weight": 1,
        "journey": "awareness — connect a reader's current task to a listed "
                   "capability only when the product row supports the link",
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
