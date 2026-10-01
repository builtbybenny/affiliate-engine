"""Product rotation + content planning.

Reads data/products.csv and decides, for a given date and format, which
product to feature. Rotation is deterministic (same date => same plan) so
GitHub Actions runs and your local runs always agree.
"""
from __future__ import annotations

import csv
from datetime import date, datetime

from core import config


def load_products() -> list[dict]:
    if not config.PRODUCTS_CSV.exists():
        raise SystemExit(
            f"Missing {config.PRODUCTS_CSV}. Add products first (see data/products.csv)."
        )
    with open(config.PRODUCTS_CSV, newline="", encoding="utf-8") as f:
        rows = [r for r in csv.DictReader(f) if r.get("name", "").strip()]
    if not rows:
        raise SystemExit("products.csv has no rows with a name.")
    return rows


def pick_product(for_date: date, format_name: str, products: list[dict]) -> dict:
    """Deterministic rotation so no product repeats until the cycle ends."""
    ordinal = for_date.toordinal()
    slot = ordinal * 2 + (0 if format_name == "carousel" else 1)
    return products[slot % len(products)]


def pick_product_lru(for_date: date, products: list[dict]) -> dict:
    """Least-recently-featured product, with ordinal rotation for ties.

    Reads the concepts history so casual scrollers see every product before
    any product repeats — this IS the repeat-exposure strategy's backbone.
    """
    from core import concepts

    h = concepts.load_history()
    last = h.get("product_last", {})

    def pid(p: dict) -> str:
        return p.get("id") or p["name"]

    n = len(products)
    start = for_date.toordinal() % n
    order = [products[(start + i) % n] for i in range(n)]
    return min(order, key=lambda p: last.get(pid(p), "0000-01-01"))


def find_by_slug(slug: str, products: list[dict]) -> dict | None:
    for p in products:
        if slugify(p.get("id") or p["name"]) == slug:
            return p
    return None


def theme_for(for_date: date, format_name: str) -> str:
    weekday = for_date.strftime("%a").lower()
    entries = config.WEEKLY_CALENDAR.get(weekday, [("carousel", "product_spotlight")])
    # If the calendar asks for another format that day, fall back to a sensible theme.
    for fmt, theme in entries:
        if fmt == format_name:
            return theme
    return entries[0][1] if entries else "product_spotlight"


def parse_benefits(product: dict) -> list[str]:
    raw = product.get("benefits", "") or ""
    return [b.strip() for b in raw.split("|") if b.strip()]


def next_filename_slug(for_date: date, format_name: str, product: dict) -> str:
    return f"{for_date.isoformat()}_{format_name}_{slugify(product.get('id') or product['name'])}"


def slugify(text: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in text.strip().lower()]
    slug = "".join(keep)
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug.strip("-") or "item"


def format_plan_time(for_date: date, format_name: str) -> datetime:
    hh, mm = config.POST_TIMES[format_name].split(":")
    return datetime(for_date.year, for_date.month, for_date.day, int(hh), int(mm))
