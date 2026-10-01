"""Central configuration: paths, env loading, weekly calendar, posting times."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
CAPTIONS_DIR = DATA_DIR / "captions"
PRODUCT_IMAGES_DIR = DATA_DIR / "product_images"
ASSETS_DIR = ROOT / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"
MUSIC_DIR = ASSETS_DIR / "music"
PUBLIC_DIR = ROOT / "public"
MEDIA_DIR = PUBLIC_DIR / "media"
CAROUSELS_DIR = MEDIA_DIR / "carousels"
REELS_DIR = MEDIA_DIR / "reels"

for d in (
    DATA_DIR, CAPTIONS_DIR, PRODUCT_IMAGES_DIR, FONTS_DIR,
    MUSIC_DIR, MEDIA_DIR, CAROUSELS_DIR, REELS_DIR,
):
    d.mkdir(parents=True, exist_ok=True)

PRODUCTS_CSV = DATA_DIR / "products.csv"
PLAN_CSV = DATA_DIR / "content_plan.csv"
PUBLISHED_LOG = DATA_DIR / "published_log.csv"
USAGE_LOG = DATA_DIR / "usage_log.csv"
HASHTAGS_TXT = DATA_DIR / "hashtags.txt"
TOKEN_ENC = DATA_DIR / "token.enc"

load_dotenv(ROOT / ".env")

# ── Credentials / platform ────────────────────────────────────────────
GRAPH_VERSION = os.getenv("GRAPH_VERSION", "v23.0")
IG_USER_ID = os.getenv("IG_USER_ID", "")
FB_PAGE_ID = os.getenv("FB_PAGE_ID", "")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN", "")
PUBLIC_BASE_URL = os.getenv("PUBLIC_MEDIA_BASE_URL", "").rstrip("/")
TOKEN_ENCRYPTION_KEY = os.getenv("TOKEN_ENCRYPTION_KEY", "")

# ── Branding (locked: no placeholders) ────────────────────────────────
BRAND_NAME = os.getenv("BRAND_NAME", "Stack & Save")
BRAND_HANDLE = os.getenv("BRAND_HANDLE", "@stackandsavehq")
NICHE = os.getenv("NICHE", "saas_tools")
TZ_OFFSET = os.getenv("TZ_OFFSET", "+05:30")

# ── Weekly content calendar (SaaS/tech edition) ──────────────────────
# weekday -> list of (format, theme). Formats: "reel" | "carousel".
# Themes map to HOOKS in core/copywriter.py.
WEEKLY_CALENDAR = {
    "mon": [("carousel", "saas_stack")],        # 5-tool stack carousel
    "tue": [("reel", "before_after")],           # workflow transformation
    "wed": [("carousel", "comparison")],          # X vs Y
    "thu": [("reel", "tutorial_teaser")],        # 15-sec how-to
    "fri": [("carousel", "free_tools")],         # free-tier roundup
    "sat": [("reel", "deal_alert")],              # lifetime deals / pricing changes
    "sun": [("carousel", "myth_vs_fact")],        # objection crushers
}

# Local posting time per format (24h). B2B audience skews earlier.
POST_TIMES = {"carousel": "11:00", "reel": "19:00"}

# Slide palettes: (bg_top, bg_bottom, accent, text) — tech/dark UI feel
PALETTES = [
    ("#0f172a", "#1e293b", "#38bdf8", "#f8fafc"),  # slate + sky (default)
    ("#0b1020", "#101935", "#8b5cf6", "#eef2ff"),  # midnight + violet
    ("#052e2b", "#0f3d3a", "#2dd4bf", "#ecfeff"),  # deep teal
    ("#1c1917", "#292524", "#f59e0b", "#fffbeb"),  # charcoal + amber
    ("#111827", "#1f2937", "#f472b6", "#fdf2f8"),  # graphite + pink
    ("#0c1428", "#16233f", "#22d3ee", "#ecfeff"),  # navy + cyan
]
PALETTES = [
    ("#0f172a", "#1e293b", "#38bdf8", "#f8fafc"),
    ("#1a1a2e", "#16213e", "#e94560", "#f1f1f1"),
    ("#0b3d2e", "#14532d", "#facc15", "#f0fdf4"),
    ("#2d1b4e", "#44318d", "#f7b731", "#f5f6fa"),
    ("#3d1e1e", "#7b2d26", "#ffd166", "#fdf6ec"),
    ("#10233f", "#205295", "#ff6b6b", "#eaf6ff"),
]


def tz() -> timezone:
    """Timezone object from TZ_OFFSET like '+05:30' or '-08:00'."""
    sign = 1 if TZ_OFFSET.strip().startswith("+") else -1
    hh, mm = TZ_OFFSET.strip().lstrip("+-").split(":")
    return timezone(sign * timedelta(hours=int(hh), minutes=int(mm)))


def now_local() -> datetime:
    return datetime.now(tz())
