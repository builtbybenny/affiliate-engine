#!/usr/bin/env python3
"""Generate the day's media: concept-driven carousels and reels.

Examples:
  python scripts/generate.py --today            # whatever the calendar says today
  python scripts/generate.py --date 2026-09-26  # preview a future day
  python scripts/generate.py --today --format carousel
  python scripts/generate.py --today --dry-run  # plan + copy only, no media
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date as _date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console; setup_console()

from core import config, copywriter, planner, concepts, llm, briefs
from media import carousel, reel


def _stock_credits() -> str:
    """Attribution owed by stock providers used during this render (first comment)."""
    try:
        from media import stock
        credits = stock.drain_credits()
        return ("\n" + "\n".join(credits)) if credits else ""
    except Exception:
        return ""


def _ensure_product_named(caption: str, product: dict) -> str:
    """Belt-and-braces: the caption must name the tool at least once.

    The AI prompt asks for it but compliance slips (2026-10-04's Pictory
    caption never said 'Pictory'). Deterministic guard: if the name is
    missing, splice a naming line in before the disclosure.
    """
    name = product["name"]
    if name.lower() in caption.lower():
        return caption
    trial = (product.get("trial") or "").strip()
    line = f"The tool: {name}" + (f" — {trial}." if trial else ".")
    marker = "Affiliate link"
    if marker in caption:
        return caption.replace(marker, f"{line}\n\n{marker}", 1)
    return f"{caption}\n\n{line}"


def apply_punch_gate(ai_copy: dict | None, template_hook: str, concept: dict,
                     product: dict, rng) -> str:
    """Pick the hook that actually ships (2026-10-05 content review).

    AI hook wins when present — the template hook is the fallback, not the
    boss. Exception: the punch gate — soft questions / hype filler lose to
    the researched or concept-bank statement. Also repairs a caption that
    still opens with a question by swapping line 1 for the gated hook.
    """
    final_hook = (ai_copy or {}).get("hook") or template_hook
    if not copywriter.punchy(final_hook):
        final_hook = (
            template_hook if copywriter.punchy(template_hook)
            else copywriter.hook_from_concept(concept, product, rng)
        )
        if ai_copy:
            ai_copy["hook"] = final_hook
    if ai_copy:
        cap_lines = ai_copy.get("caption", "").split("\n")
        if cap_lines and cap_lines[0].strip().endswith("?"):
            cap_lines[0] = final_hook
            ai_copy["caption"] = "\n".join(cap_lines)
    return final_hook


def plan_slot(for_date: _date, fmt: str, products: list[dict], record: bool = True) -> dict:
    """Decide product + concept for a slot and return the plan dict."""
    product = planner.pick_product_lru(for_date, products)
    rng = random.Random(for_date.toordinal() * 7 + len(fmt))
    concept_id, is_rerun = concepts.pick_concept(product, fmt, for_date, rng, record=record)
    return {
        "date": for_date.isoformat(),
        "format": fmt,
        "product_id": product.get("id") or product["name"],
        "concept": concept_id,
        "is_rerun": is_rerun,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--today", action="store_true")
    ap.add_argument("--date", type=str, default="")
    ap.add_argument("--format", choices=["carousel", "reel"], default="")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    for_date = (
        _date.fromisoformat(args.date)
        if args.date
        else (config.now_local().date() if args.today or not args.date else _date.today())
    )

    products = planner.load_products()
    formats = [args.format] if args.format else [f for f, _ in config.WEEKLY_CALENDAR.get(for_date.strftime("%a").lower(), [("carousel", "stack_drop")])]

    plans: list[dict] = []
    for fmt in formats:
        plan = plan_slot(for_date, fmt, products, record=not args.dry_run)
        plans.append(plan)

        product = planner.find_by_slug(plan["product_id"], products) or products[0]
        concept = concepts.CONCEPTS[plan["concept"]]
        rng = random.Random(for_date.toordinal() + (0 if fmt == "carousel" else 1))

        # Research brief (core/briefs): real blog facts + search keywords
        # for THIS product, refreshed weekly in CI and lazily when stale.
        # The static hook bank was dumped 2026-10-05 — hooks are now written
        # and retention-scored per post (llm.pick_retention_hook).
        try:
            brief = briefs.get(product, refresh=not args.dry_run)
        except Exception:
            brief = {}
        brief_note = (
            f"{len(brief.get('keywords', []))} kw / {len(brief.get('facts', []))} facts"
            + (" (stale)" if brief.get("stale") else "")
        ) if brief else "none"

        # Template hook: concept bank as fallback when AI copy is down.
        hook = copywriter.hook_from_concept(concept, product, rng)

        print(f"\n[{for_date}] {fmt.upper()} | concept={concept['label']} | product={product['name']}"
              + ("  (honest rerun)" if plan["is_rerun"] else ""))
        print(f"  brief  : {brief_note}")

        if args.dry_run:
            print("  hook   :", hook)
            print("  slides :", " | ".join(copywriter.build_slide_texts(product, plan["concept"], rng, hook=hook)[:4]))
            continue

        first_comment = copywriter.build_first_comment(product, rng)

        ai_copy = llm.write_copy(
            product,
            plan["concept"],
            fallback_hooks=concept["hooks"],
            fallback_slides=[],
            fallback_caption="",
            brief=brief,
        )
        if ai_copy:
            print("  copy: AI (Gemini)")
        else:
            print("  copy: templates")

        final_hook = apply_punch_gate(ai_copy, hook, concept, product, rng)

        if fmt == "carousel":
            files, texts = carousel.build_carousel(
                product, plan["concept"], for_date=for_date, copy_override=ai_copy,
                hook_override=final_hook,
            )
            first_comment += _stock_credits()
            caption = (
                ai_copy["caption"]
                if ai_copy
                else copywriter.build_caption(
                    product, plan["concept"], for_date, rng,
                    include_hashtags=False, hook=hook,
                )
            )
            caption = _ensure_product_named(caption, product)
            (files[0].parent / "caption.txt").write_text(caption, encoding="utf-8")
            (files[0].parent / "first_comment.txt").write_text(first_comment, encoding="utf-8")
            plan["out_dir"] = str(files[0].parent)
            print(f"  wrote {len(files)} slides + caption + comment -> {files[0].parent}")
        else:
            path, _ = reel.build_reel(
                product, plan["concept"], for_date=for_date, copy_override=ai_copy,
                hook_override=final_hook,
            )
            first_comment += _stock_credits()
            caption = (
                ai_copy["caption"]
                if ai_copy
                else copywriter.build_caption(
                    product, plan["concept"], for_date, rng,
                    include_hashtags=False, hook=hook,
                )
            )
            caption = _ensure_product_named(caption, product)
            path.with_name(path.stem + "_caption.txt").write_text(caption, encoding="utf-8")
            path.with_name(path.stem + "_comment.txt").write_text(first_comment, encoding="utf-8")
            plan["out_file"] = str(path)
            print(f"  wrote {path} + comment")

    # Persist plans so publish.py serves exactly what was planned
    # (dry-runs plan but never mutate concept history).
    if args.dry_run:
        print("\n(dry run - no history recorded)")
        return
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    plan_file = config.DATA_DIR / "plan.json"
    prev: list[dict] = []
    if plan_file.exists():
        try:
            prev = [
                p for p in json.loads(plan_file.read_text(encoding="utf-8"))
                if p.get("date") != for_date.isoformat()
            ]
        except Exception:
            prev = []
    plan_file.write_text(json.dumps(prev + plans, indent=2), encoding="utf-8")

    print("\nNext: python scripts/publish.py --today")


if __name__ == "__main__":
    main()
