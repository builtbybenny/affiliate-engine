#!/usr/bin/env python3
"""Writes verification results to data/_verify.json (immune to console garbling).

Always exits 0 and always writes the JSON file, even on unexpected errors —
the JSON IS the ground truth, not the console.
"""
import json
import random
import subprocess
import sys
import traceback
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console  # noqa: E402

setup_console()

OUT = Path(__file__).resolve().parent.parent / "data" / "_verify.json"
out: dict = {"checks": [], "error": ""}

try:
    from core import concepts, planner

    products = planner.load_products()
    out["checks"].append({
        "name": "csv_columns_align",
        "ok": products[0].get("alt", "") != "" and products[0].get("trial", "") != "",
        "alts_sample": [p["alt"] for p in products][:3],
    })

    # clean slate for simulation (and for production launch afterwards)
    if concepts.HISTORY.exists():
        concepts.HISTORY.unlink()

    d0 = date(2026, 10, 1)
    seq = []
    for i in range(12):
        d = d0 + timedelta(days=i)
        fmt = "carousel" if i % 2 == 0 else "reel"
        p = planner.pick_product_lru(d, products)
        rng = random.Random(d.toordinal() * 7 + len(fmt))
        cid, rerun = concepts.pick_concept(p, fmt, d, rng)
        seq.append({"day": d.isoformat(), "product": p["id"], "concept": cid, "rerun": rerun})

    n_prod = len(products)
    firstN, later = seq[:n_prod], seq[n_prod:]
    out["checks"].append({
        "name": f"lru_all_{n_prod}_products_first{n_prod}_no_reruns",
        "ok": len({s["product"] for s in firstN}) == n_prod and not any(s["rerun"] for s in firstN),
        "order": [s["product"] for s in firstN],
    })
    out["checks"].append({
        "name": "repeats_get_honest_rerun_framing",
        "ok": all(s["rerun"] for s in later),
        "later": later,
    })
    pairs = [(s["concept"], s["product"]) for s in firstN]
    out["checks"].append({"name": "no_pairing_repeats_firstN", "ok": len(set(pairs)) == n_prod})

    # dry-run purity: record=False must not ADD pairings
    rng = random.Random(1)
    before = len(concepts.load_history().get("pairings", []))
    concepts.pick_concept(products[0], "carousel", d0, rng, record=False)
    after = len(concepts.load_history().get("pairings", []))
    out["checks"].append({
        "name": "dry_run_leaves_history_unchanged",
        "ok": before == after,
        "before": before,
        "after": after,
    })

    # media factories still function with concept hooks
    from media.lead import build_lead_carousel
    lead_dir, lead_paths = build_lead_carousel("free_ai_apps", for_seed=11)
    out["checks"].append({
        "name": "lead_carousel_renders",
        "ok": len(lead_paths) >= 5 and (lead_dir / "caption.txt").exists(),
        "slides": len(lead_paths),
    })

    # stock-photo integration (Pexels): live fetch + disk cache + slide usage
    from media import stock
    if stock.available():
        img = stock.product_background(products[0], portrait=True)
        list_img = stock.list_background("ai")
        out["checks"].append({
            "name": "pexels_stock_fetch_and_cache",
            "ok": img is not None and list_img is not None,
            "cached_files": len(list(stock.CACHE_DIR.glob("*.jpg"))),
            "product_photo": img is not None,
            "list_photo": list_img is not None,
        })
    else:
        out["checks"].append({"name": "pexels_stock_fetch_and_cache", "ok": True, "skipped": "no PEXELS_API_KEY"})

    from media import carousel as car
    prod = products[0]  # catalog-agnostic: test against whatever is first
    files, texts = car.build_carousel(
        prod, "stack_drop",
        out_dir=Path("_tmp_verify_car"), for_date=d0, seed=5,
        hook_override=f"You keep asking about {prod['name']} - here it is again",
    )
    out["checks"].append({
        "name": "carousel_renders_with_rerun_hook",
        "ok": len(files) >= 4 and files[0].exists(),
        "slides": len(files),
    })

    # reel factory renders end-to-end (short 4s clip: photo bg + chrome + ffmpeg)
    try:
        from media.reel import build_reel
        reel_path, reel_caption = build_reel(
            prod, "tutorial_teaser", for_date=d0, seed=9, duration=4.0,
        )
        out["checks"].append({
            "name": "reel_renders",
            "ok": reel_path.exists() and reel_path.stat().st_size > 100_000,
            "path": reel_path.name,
            "bytes": reel_path.stat().st_size if reel_path.exists() else 0,
            "caption_words": len(reel_caption.split()),
        })
    except Exception as e:
        out["checks"].append({"name": "reel_renders", "ok": False, "err": repr(e)[:300]})

    # radar artifacts exist
    radar_files = list((Path(__file__).parent.parent / "data").glob("radar_digest_*.md"))
    cand = Path(__file__).parent.parent / "data" / "radar_candidates.json"
    out["checks"].append({
        "name": "radar_artifacts_present",
        "ok": bool(radar_files) and cand.exists(),
        "digests": [f.name for f in radar_files],
    })

    # compile gate
    r = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", "core", "media", "publishers", "scripts"],
        capture_output=True, text=True,
    )
    out["checks"].append({"name": "compileall", "ok": r.returncode == 0, "err": r.stderr[-300:]})

except Exception:
    out["error"] = traceback.format_exc()[-1500:]

finally:
    # production starts with a pristine concept history
    try:
        from core import concepts as _c
        _c.HISTORY.write_text(json.dumps({"pairings": [], "product_last": {}}), encoding="utf-8")
    except Exception:
        pass

out["all_ok"] = (not out["error"]) and all(c.get("ok") for c in out["checks"])
OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
