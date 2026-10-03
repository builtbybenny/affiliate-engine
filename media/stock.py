"""Stock media backgrounds — multi-provider, free tier only, cached forever.

Photo providers (tried in a salt-rotated order so the feed gets variety):
  openverse  keyless, mirrors Rawpixel/StockSnap CC0 pools (always on)
  pexels     PEXELS_API_KEY
  unsplash   UNSPLASH_ACCESS_KEY (free, 50 req/hr demo — plenty, we cache)
  vecteezy   VECTEEZY_API_KEY + VECTEEZY_ACCOUNT_ID (free tier: 500 dl/mo,
             attribution required -> credit drained into the first comment)

Variety: every fetch takes a `salt` (post date). The salt rotates the
provider order, the result page, and the cache key, so two posts on the
same topic get different images — no more "every slide looks the same".

Video: `video_bg_frames()` gives real stock footage for reel backgrounds
(Pexels video endpoint, same key as photos). None on any failure — the
reel falls back to the Ken Burns still, so posting never stalls.

Every downloaded file is cached in data/stock/ (photos) or
data/stock/video/ (clips, pruned to the newest few) — each URL is
fetched once, ever.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import time
import zlib
from pathlib import Path

import requests

from PIL import Image, ImageOps

from core import config

CACHE_DIR = config.DATA_DIR / "stock"
CACHE_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_CACHE = CACHE_DIR / "video"
VIDEO_CACHE.mkdir(parents=True, exist_ok=True)
VIDEO_KEEP = 6  # local disk guardrail: newest N clips retained

PEXELS_API = "https://api.pexels.com/v1/search"
PEXELS_VIDEO_API = "https://api.pexels.com/videos/search"
UNSPLASH_API = "https://api.unsplash.com/search/photos"
OPENVERSE_API = "https://api.openverse.org/v1/images/"
VECTEEZY_API = "https://api.vecteezy.com"

UA = "StackAndSave/1.0 (affiliate content engine)"

# Providers that legally need a credit line when their free tier is used.
# The credit is appended to the auto-posted first comment by generate.py.
_credit_required = {"vecteezy"}
_credits: list[str] = []

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
    """True when at least one photo provider can serve a request."""
    return bool(providers())


def providers() -> list[str]:
    """Configured photo providers in this run's rotation order."""
    configured = ["openverse"]  # keyless, always available
    if os.getenv("PEXELS_API_KEY", "").strip():
        configured.append("pexels")
    if os.getenv("UNSPLASH_ACCESS_KEY", "").strip():
        configured.append("unsplash")
    if os.getenv("VECTEEZY_API_KEY", "").strip() and os.getenv("VECTEEZY_ACCOUNT_ID", "").strip():
        configured.append("vecteezy")
    # Rotate by salt so consecutive posts lead with different sources.
    salt_n = abs(zlib.crc32(str(int(time.time() // 3600)).encode()))  # hourly shift
    k = salt_n % len(configured)
    return configured[k:] + configured[:k]


def drain_credits() -> list[str]:
    """Credits owed for media used since the last call (first comment)."""
    global _credits
    out, _credits = _credits, []
    return out


def _add_credit(text: str) -> None:
    if text and text not in _credits:
        _credits.append(text)


def _slug(text: str) -> str:
    keep = [c for c in text.strip().lower() if c.isalnum() or c in "-_"]
    return "".join(keep)[:48] or "q"


def _cache_path(provider: str, query: str, portrait: bool, salt: str) -> Path:
    key = hashlib.sha1(f"{provider}|{query}|{'p' if portrait else 'l'}|{salt}".encode()).hexdigest()[:16]
    return CACHE_DIR / f"{provider}_{key}.jpg"


def _page_for(salt: str, query: str) -> int:
    """Deterministic page variety: same query, different day -> different result page."""
    h = zlib.crc32(f"{salt}|{query}".encode())
    return (h % 4) + 1


# ── providers: each returns (direct_url, credit_or_None) or None ─────────────

def _search_pexels(query: str, portrait: bool, page: int) -> tuple[str, None] | None:
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    try:
        r = requests.get(
            PEXELS_API,
            params={"query": query, "per_page": 8, "page": page,
                    "orientation": "portrait" if portrait else "landscape", "size": "large"},
            headers={"Authorization": key, "User-Agent": UA},
            timeout=20,
        )
        if r.status_code != 200:
            return None
        for p in r.json().get("photos") or []:
            src = p.get("src") or {}
            url = src.get("large2x") or src.get("large") or src.get("original")
            if url:
                return url, None
    except Exception:
        return None
    return None


def _search_unsplash(query: str, portrait: bool, page: int) -> tuple[str, None] | None:
    key = os.getenv("UNSPLASH_ACCESS_KEY", "").strip()
    if not key:
        return None
    try:
        r = requests.get(
            UNSPLASH_API,
            params={"query": query, "per_page": 10, "page": page,
                    "orientation": "portrait" if portrait else "landscape"},
            headers={"Authorization": f"Client-ID {key}", "User-Agent": UA},
            timeout=20,
        )
        if r.status_code != 200:
            return None
        for p in r.json().get("results") or []:
            raw = ((p.get("urls") or {}).get("raw") or "").strip()
            if raw:
                # imgix params on the raw URL -> right-sized JPEG, no huge originals
                url = f"{raw}&fm=jpg&fit=max&w=1800&q=80"
                # Unsplash API guidelines: trigger the download endpoint
                try:
                    requests.get(f"https://api.unsplash.com/photos/{p.get('id')}/download?client_id={key}",
                                 timeout=10)
                except Exception:
                    pass
                return url, None
    except Exception:
        return None
    return None


def _search_openverse(query: str, portrait: bool, page: int) -> tuple[str, None] | None:
    # Public domain / CC0 only (Rawpixel, StockSnap, ...) — no attribution owed.
    params = {"q": query, "page_size": 20, "page": page,
              "license": "cc0,pdm", "category": "photograph", "size": "large"}
    if portrait:
        params["aspect_ratio"] = "tall"
    try:
        r = requests.get(OPENVERSE_API, params=params, headers={"User-Agent": UA}, timeout=20)
        if r.status_code != 200:
            return None
        for item in r.json().get("results") or []:
            url = (item.get("url") or "").strip()
            if url:
                return url, None
    except Exception:
        return None
    return None


def _search_vecteezy(query: str, portrait: bool, page: int) -> tuple[str, str] | None:
    token = os.getenv("VECTEEZY_API_KEY", "").strip()
    account = os.getenv("VECTEEZY_ACCOUNT_ID", "").strip()
    if not token or not account:
        return None
    headers = {"Authorization": f"Bearer {token}", "User-Agent": UA}
    try:
        r = requests.get(
            f"{VECTEEZY_API}/v2/{account}/resources",
            params={"term": query, "content_type": "photo", "page": page, "per_page": 20,
                    "orientation": "vertical" if portrait else "horizontal",
                    "license_type": "commercial", "family_friendly": True},
            headers=headers,
            timeout=20,
        )
        if r.status_code != 200:
            return None
        body = r.json()
        items = body.get("results") or body.get("data") or body.get("resources") or body.get("items") or []
        if isinstance(items, dict):
            items = items.get("items") or items.get("results") or []
        if not items:
            return None
        item = items[0]
        rid = item.get("id")
        if not rid:
            return None
        # Download endpoint -> fresh URL (counts against the free 500/month)
        d = requests.get(
            f"{VECTEEZY_API}/v2/{account}/resources/{rid}/download",
            headers=headers, timeout=20,
        )
        if d.status_code != 200:
            return None
        dbody = d.json()
        file_url = next(
            (dbody[k] for k in ("url", "download_url", "file_url", "link")
             if isinstance(dbody.get(k), str) and dbody[k].startswith("http")),
            None,
        )
        if not file_url:
            return None
        author = next(
            (str(item[k]) for k in ("author", "creator", "user_name")
             if item.get(k)),
            "",
        )
        credit = f"Photo by {author} on Vecteezy" if author else "Photo: Vecteezy.com"
        return file_url, credit
    except Exception:
        return None


_SEARCHERS = {
    "pexels": _search_pexels,
    "unsplash": _search_unsplash,
    "openverse": _search_openverse,
    "vecteezy": _search_vecteezy,
}


# ── download + cache ─────────────────────────────────────────────────────────

def _download(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, headers={"User-Agent": UA}, timeout=30)
        if r.status_code != 200 or len(r.content) < 20_000:
            return False
        dest.write_bytes(r.content)
        with Image.open(dest) as im:
            im.verify()
        return True
    except Exception:
        try:
            dest.unlink(missing_ok=True)
        except Exception:
            pass
        return False


def fetch_photo(query: str, portrait: bool = True, salt: str = "") -> Image.Image | None:
    """Cached multi-provider fetch: query -> photo (RGB). None when everything fails."""
    for provider in providers():
        dest = _cache_path(provider, query, portrait, salt)
        if dest.exists():
            try:
                img = Image.open(dest).convert("RGB")
                if provider in _credit_required:
                    _add_credit(_credit_text_for(provider, dest))
                return img
            except Exception:
                try:
                    dest.unlink(missing_ok=True)
                except Exception:
                    pass
        found = _SEARCHERS[provider](query, portrait, _page_for(salt or "x", query))
        if not found:
            continue
        url, credit = found
        if _download(url, dest):
            if credit:
                dest.with_suffix(".credit").write_text(credit, encoding="utf-8")
                _add_credit(credit)
            try:
                return Image.open(dest).convert("RGB")
            except Exception:
                continue
    return None


def _credit_text_for(provider: str, dest: Path) -> str:
    meta = dest.with_suffix(".credit")
    if meta.exists():
        try:
            return meta.read_text(encoding="utf-8").strip()
        except Exception:
            pass
    return "Photo: Vecteezy.com"


# ── topic mapping + public helpers ───────────────────────────────────────────

def _topic_for(product: dict) -> str:
    """Map a product row to the closest visual topic via keyword hits."""
    haystack = " ".join(
        str(product.get(k, "")).lower()
        for k in ("name", "benefits", "specs", "id")
    )
    for topic, words in {
        "design": ("design", "graphic", "figma"),
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


def topic_query(product: dict) -> str:
    """The primary search phrase for a product (used for photos AND video)."""
    return _TOPIC_QUERIES[_topic_for(product)]


def product_background(product: dict, portrait: bool = True, salt: str = "") -> Image.Image | None:
    """Best stock photo for this product's vibe; None if unavailable."""
    query = topic_query(product)
    queries = [query, *_DEFAULT_QUERIES]
    for q in queries:
        img = fetch_photo(q, portrait=portrait, salt=salt)
        if img is not None:
            return ImageOps.exif_transpose(img)
    return None


def list_background(list_keyword_hint: str, salt: str = "") -> Image.Image | None:
    """Stock photo for a lead-magnet list (e.g. 'free ai apps')."""
    queries = [f"{list_keyword_hint} apps on phone screen", *_DEFAULT_QUERIES]
    for q in queries:
        img = fetch_photo(q, portrait=True, salt=salt)
        if img is not None:
            return ImageOps.exif_transpose(img)
    return None


# ── stock video backgrounds for reels ────────────────────────────────────────

def _prune_videos(keep: int = VIDEO_KEEP) -> None:
    clips = sorted(VIDEO_CACHE.glob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in clips[keep:]:
        try:
            old.unlink(missing_ok=True)
        except Exception:
            pass


def _search_pexels_video(query: str, page: int, need_sec: float) -> tuple[str, float] | None:
    """A portrait clip long enough for the reel, or None."""
    key = os.getenv("PEXELS_API_KEY", "").strip()
    if not key:
        return None
    try:
        r = requests.get(
            PEXELS_VIDEO_API,
            params={"query": query, "orientation": "portrait", "per_page": 10, "page": page},
            headers={"Authorization": key, "User-Agent": UA},
            timeout=20,
        )
        if r.status_code != 200:
            return None
        candidates = []
        for v in r.json().get("videos") or []:
            dur = float(v.get("duration") or 0)
            if dur < need_sec or dur > 45:
                continue
            files = [f for f in (v.get("video_files") or [])
                     if (f.get("file_type") == "video/mp4" and f.get("link"))]
            if not files:
                continue
            # prefer portrait, then the smallest file >= 1080 on the short side
            files.sort(key=lambda f: ((f.get("height") or 0) <= (f.get("width") or 0),
                                      abs((f.get("height") or 0) - 1920)))
            candidates.append((files[0]["link"], dur))
        if candidates:
            return candidates[0]
    except Exception:
        return None
    return None


def video_bg_frames(product: dict, salt: str, need_frames: int, w: int, h: int,
                    fps: int, tmpdir: Path) -> list[Path] | None:
    """Extract `need_frames` background frames from stock footage, or None.

    Any failure (no key, no match, too-short clip, ffmpeg hiccup) returns
    None so the reel falls back to the photo Ken Burns path.
    """
    tmpdir = Path(tmpdir)
    query = topic_query(product)
    need_sec = need_frames / float(fps) + 1.0
    page = _page_for(salt or "x", query)
    found = None
    for p in (page, 1):  # wanted page first, then a stable fallback
        found = _search_pexels_video(query, p, need_sec)
        if found:
            break
    if not found:
        return None
    url, _dur = found

    clip = VIDEO_CACHE / f"{_slug(query)}_{zlib.crc32(url.encode()) & 0xffffffff:08x}.mp4"
    if not clip.exists():
        try:
            r = requests.get(url, headers={"User-Agent": UA}, timeout=60)
            if r.status_code != 200 or len(r.content) < 200_000:
                return None
            clip.write_bytes(r.content)
            _prune_videos()
        except Exception:
            return None

    out_pattern = tmpdir / "bg_%05d.jpg"
    try:
        proc = subprocess.run(
            ["ffmpeg", "-y", "-i", str(clip),
             "-vf", f"fps={fps},scale={w}:{h}:force_original_aspect_ratio=increase,"
                    f"crop={w}:{h}",
             "-frames:v", str(need_frames),
             str(out_pattern)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=180,
        )
        if proc.returncode != 0:
            return None
    except Exception:
        return None

    frames = sorted(tmpdir.glob("bg_*.jpg"))
    if len(frames) < int(need_frames * 0.9):
        return None  # clip too short after crop -> let the caller use Ken Burns
    return frames
