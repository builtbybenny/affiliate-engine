"""Stock photo backgrounds via the Pexels API (free tier, no card).

When PEXELS_API_KEY is set, slides and reels automatically get real,
license-free photography as backgrounds instead of flat gradients.
Every fetch is cached on disk (data/stock/) so a photo is downloaded
once, ever. Every failure path silently falls back to gradients, so
the system never stalls on the network.
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

import requests

from PIL import Image, ImageOps

from core import config

CACHE_DIR = config.DATA_DIR / "stock"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

API = "https://api.pexels.com/v1/search"

# Per-topic search terms: real, hands-on scenes (not 3D renders).
# Topics chosen to match the product-type words in our catalog.
_TOPIC_QUERIES = {
    "design": "designer working on laptop creative workspace",
    "video": "content creator filming video editing desk",
    "email": "marketer checking email analytics on screen",
    "website": "developer building website code editor",
    "sell": "small business owner online store packing orders",
    "course": "person recording online course at desk",
    "social": "social media manager phone content planning",
    "automation": "workflow automation laptop modern office",
    "ai": "person using ai assistant on laptop",
    "productivity": "clean minimal desk setup laptop notebook",
}

_DEFAULT_QUERIES = [
    "modern workspace laptop coffee",
    "person working laptop bright office",
    "minimal desk setup technology",
    "creative professional computer screen",
]


def available() -> bool:
    return bool(os.getenv("PEXELS_API_KEY", "").strip())


def _cache_path(query: str, portrait: bool) -> Path:
    key = hashlib.sha1(f"{query}|{'p' if portrait else 'l'}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"{key}.jpg"


def _search(query: str, portrait: bool) -> str | None:
    """Return a direct image URL for the query, or None on any failure."""
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    for attempt in (1, 2):  # one retry on transient errors
        try:
            r = requests.get(
                API,
                params={
                    "query": query,
                    "per_page": 6,
                    "orientation": "portrait" if portrait else "landscape",
                    "size": "large",
                },
                headers={"Authorization": key},
                timeout=20,
            )
            if r.status_code == 200:
                photos = r.json().get("photos") or []
                for p in photos:
                    src = (p.get("src") or {})
                    url = src.get("large2x") or src.get("large") or src.get("original")
                    if url:
                        return url
                return None  # valid response, zero results
            if r.status_code in (429, 500, 502, 503) and attempt == 1:
                time.sleep(2)
                continue
            return None
        except Exception:
            if attempt == 1:
                time.sleep(2)
                continue
            return None
    return None


def _download(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, timeout=30)
        if r.status_code != 200 or len(r.content) < 20_000:
            return False
        dest.write_bytes(r.content)
        # verify it actually decodes as an image
        with Image.open(dest) as im:
            im.verify()
        return True
    except Exception:
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def fetch_photo(query: str, portrait: bool = True) -> Image.Image | None:
    """Cached fetch: query -> photo (RGB). None when key missing/offline."""
    dest = _cache_path(query, portrait)
    if dest.exists():
        try:
            return Image.open(dest).convert("RGB")
        except Exception:
            try:
                dest.unlink(missing_ok=True)
            except Exception:
                pass
    url = _search(query, portrait)
    if not url:
        return None
    if not _download(url, dest):
        return None
    try:
        return Image.open(dest).convert("RGB")
    except Exception:
        return None


def _topic_for(product: dict) -> str:
    """Map a product row to the closest visual topic via keyword hits."""
    haystack = " ".join(
        str(product.get(k, "")).lower()
        for k in ("name", "benefits", "specs", "id")
    )
    for topic, words in {
        "design": ("design", "canva", "graphic", "figma"),
        "video": ("video", "film", "reel", "edit"),
        "email": ("email", "mail", "newsletter"),
        "website": ("website", "builder", "landing", "host", "web"),
        "sell": ("sell", "store", "ecommerce", "cart", "shop", "funnel"),
        "course": ("course", "teach", "academy", "kajabi", "learn"),
        "social": ("social", "instagram", "schedule", "buffer"),
        "automation": ("automat", "workflow", "zap", "integrat"),
        "ai": ("ai", "gpt", "assistant", "bot"),
    }.items():
        if any(w in haystack for w in words):
            return topic
    return "productivity"


def product_background(product: dict, portrait: bool = True) -> Image.Image | None:
    """Best stock photo for this product's vibe; None if unavailable."""
    topic = _topic_for(product)
    queries = [_TOPIC_QUERIES[topic], *_DEFAULT_QUERIES]
    for q in queries:
        img = fetch_photo(q, portrait=portrait)
        if img is not None:
            return ImageOps.exif_transpose(img)
    return None


def list_background(list_keyword_hint: str) -> Image.Image | None:
    """Stock photo for a lead-magnet list (e.g. 'free ai apps')."""
    queries = [f"{list_keyword_hint} apps on phone screen", *_DEFAULT_QUERIES]
    for q in queries:
        img = fetch_photo(q, portrait=True)
        if img is not None:
            return ImageOps.exif_transpose(img)
    return None
