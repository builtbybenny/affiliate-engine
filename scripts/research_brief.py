#!/usr/bin/env python3
"""Refresh research briefs: harvest blogs/news -> per-product SEO briefs.

Replaces scripts/hook_research.py (hook bank dumped 2026-10-05). Instead of
distilling template hooks, this grounds each product's captions in what the
internet actually publishes about it:

  python scripts/research_brief.py            # refresh stale products only
  python scripts/research_brief.py --all      # rebuild every product (CI)
  python scripts/research_brief.py --product framer

Automated: .github/workflows/weekly-evolve.yml (Sundays).
Failure mode: keeps existing briefs untouched and exits 0 — the posting
pipeline never depends on this succeeding (stale briefs keep serving).
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console  # noqa: E402

setup_console()

from core import briefs, llm, planner  # noqa: E402


def main() -> None:
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="rebuild every product")
    ap.add_argument("--product", type=str, default="", help="rebuild one product id")
    args = ap.parse_args()

    if not llm.available():
        print("no GEMINI_API_KEY — cannot distill briefs (keeping existing)")
        return

    products = planner.load_products()
    if args.product:
        products = [p for p in products
                    if (p.get("id") or p.get("name", "")).lower() == args.product.lower()]
        if not products:
            print(f"unknown product: {args.product}")
            return
        args.all = True

    if args.all:
        print(f"research briefs: rebuilding {len(products)} products")
        briefs.refresh_all(products)
    else:
        stale = []
        for p in products:
            b = briefs.get(p, refresh=False)
            if not b or b.get("stale"):
                stale.append(p)
        print(f"research briefs: {len(products) - len(stale)} fresh, "
              f"{len(stale)} stale/missing")
        if stale:
            briefs.refresh_all(stale)

    n, updated = briefs.status()
    print(f"briefs: {n} products on disk (updated {updated[:19] or 'never'})")


if __name__ == "__main__":
    main()
