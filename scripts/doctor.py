#!/usr/bin/env python3
"""System doctor: audits the whole pipeline and prints YOUR exact manual steps.

Run anytime:  python scripts/doctor.py
Add --live to also ping the Instagram API with your stored token.
"""
from __future__ import annotations

import argparse
import csv
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console  # noqa: E402

setup_console()

from core import config  # noqa: E402

OK, BAD, WARN = "[ok]  ", "[todo]", "[warn]"

checks: list[tuple[str, str, str]] = []  # (status, label, detail)


def add(status: str, label: str, detail: str = "") -> None:
    checks.append((status, label, detail))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", action="store_true", help="also verify the Meta token via API")
    args = ap.parse_args()

    # ── 1. Credentials ────────────────────────────────────────────────
    env_path = config.ROOT / ".env"
    if env_path.exists():
        add(OK, ".env exists")
    else:
        add(BAD, ".env missing", "copy .env.example to .env (one command, below)")

    if config.IG_USER_ID and config.FB_PAGE_ID and config.ACCESS_TOKEN:
        add(OK, "Meta credentials present (IG + FB + token)")
        if args.live:
            _live_check()
    else:
        add(BAD, "Meta credentials incomplete", "run: python scripts/setup_tokens.py")

    # ── 2. Runtime deps ───────────────────────────────────────────────
    for mod in ("PIL", "requests", "dotenv", "cryptography"):
        try:
            __import__(mod)
            add(OK, f"python package: {mod}")
        except ImportError:
            add(BAD, f"python package missing: {mod}", "pip install -r requirements.txt")

    if shutil.which("ffmpeg") or Path(config.ROOT, "ffmpeg.exe").exists():
        add(OK, "ffmpeg (reel renderer)")
    else:
        add(BAD, "ffmpeg missing", "winget install Gyan.FFmpeg  (or brew/apt)")

    # ── 3. Content data ───────────────────────────────────────────────
    try:
        with open(config.PRODUCTS_CSV, newline="", encoding="utf-8") as f:
            rows = [r for r in csv.DictReader(f) if r.get("name", "").strip()]
        add(OK, f"products.csv: {len(rows)} products")
        bad_links = [r["id"] for r in rows if "yourref" in (r.get("url") or "")]
        if bad_links:
            add(BAD, "affiliate links are placeholders", f"replace URL column for: {', '.join(bad_links)}")
        else:
            add(OK, "all affiliate links look swapped-in")
        missing_alt = [r["id"] for r in rows if not (r.get("alt") or "").strip()]
        if missing_alt:
            add(WARN, "products without competitor ('alt') — comparison posts disabled for them", ", ".join(missing_alt))
    except FileNotFoundError:
        add(BAD, "products.csv missing")

    if config.HASHTAGS_TXT.exists():
        n = len([l for l in config.HASHTAGS_TXT.read_text(encoding="utf-8").splitlines() if l.strip()])
        add(OK, f"hashtags.txt: {n} tags")
    else:
        add(BAD, "hashtags.txt missing")

    # ── 4. Render readiness ───────────────────────────────────────────
    from media import common as media_common

    if media_common.find_font(weight="black"):
        add(OK, f"fonts found (black weight: {Path(media_common.find_font(weight='black')).name})")
    elif media_common.find_font():
        add(WARN, "only system font found — slides work but look generic",
            "drop Inter-Black.ttf / Inter-Bold.ttf / Inter-Regular.ttf into assets/fonts/ (see TOOLKIT.md)")
    else:
        add(BAD, "no font found", "drop a .ttf into assets/fonts/")

    music = list(config.MUSIC_DIR.glob("*.mp3")) + list(config.MUSIC_DIR.glob("*.m4a"))
    if music:
        add(OK, f"reel music: {len(music)} track(s) in assets/music/")
    else:
        add(WARN, "no reel music — reels render silent",
            "drop 1-2 royalty-free .mp3 into assets/music/ (links in TOOLKIT.md)")

    try:
        import os as _os
        if _os.getenv("GEMINI_API_KEY", "").strip():
            add(OK, "AI copywriter: Gemini key present (AI captions/hooks active)")
        else:
            add(WARN, "AI copywriter off — using built-in templates",
                "optional: free key at aistudio.google.com/app/apikey, add GEMINI_API_KEY to .env")
        if _os.getenv("PEXELS_API_KEY", "").strip():
            add(OK, "stock photos: Pexels key present (real photo backgrounds active)")
        else:
            add(WARN, "stock photos off — slides use branded gradients",
                "optional: free key at pexels.com/api, add PEXELS_API_KEY to .env")
    except Exception:
        pass

    imgs = list(config.PRODUCT_IMAGES_DIR.glob("*")) if config.PRODUCT_IMAGES_DIR.exists() else []
    if imgs:
        add(OK, f"product images: {len(imgs)} in data/product_images/")
    else:
        add(WARN, "no product images — posts render on branded gradients",
            "save tool screenshots as data/product_images/<id>.jpg")

    recs = list((config.ROOT / "data" / "screen_recordings").glob("*")) if (config.ROOT / "data" / "screen_recordings").exists() else []
    if recs:
        add(OK, f"screen recordings: {len(recs)} (reels will open with real UI)")
    else:
        add(WARN, "no screen recordings — reels use motion-graphics mode",
            "optional: data/screen_recordings/<id>.mp4 (60s of the tool in use)")

    avatar = config.PUBLIC_DIR / "brand" / "avatar.png"
    if avatar.exists():
        add(OK, "brand avatar generated (public/brand/avatar.png)")
    else:
        add(BAD, "brand avatar missing", "run: python scripts/make_brand_assets.py")

    # ── 5. Automation ─────────────────────────────────────────────────
    wf = config.ROOT / ".github" / "workflows" / "scheduler.yml"
    if wf.exists():
        add(OK, "scheduler workflow present")
    else:
        add(BAD, "scheduler workflow missing")

    try:
        remote = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if remote:
            add(OK, f"git remote: {remote}")
        else:
            add(BAD, "no git remote", "create the GitHub repo (steps below)")
    except Exception:
        add(BAD, "git not available")

    pages_cfg = bool(config.PUBLIC_BASE_URL)
    if pages_cfg:
        add(OK, f"public media URL: {config.PUBLIC_BASE_URL}")
    else:
        add(WARN, "PUBLIC_MEDIA_BASE_URL not set (fine until first GitHub publish)")

    # ── Report ────────────────────────────────────────────────────────
    print("=" * 66)
    print(" SYSTEM DOCTOR — affiliate engine audit")
    print("=" * 66)
    for status, label, detail in checks:
        print(f" {status} {label}")
        if detail:
            print(f"        -> {detail}")

    todos = [c for c in checks if c[0] == BAD]
    warns = [c for c in checks if c[0] == WARN]
    print("\n" + "-" * 66)
    if not todos:
        print("ALL CRITICAL CHECKS PASS. The machine can run.")
    else:
        print(f"{len(todos)} CRITICAL ITEM(S) — your manual steps, in order:\n")

    step = 1
    if any("placeholder" in c[1] or "placeholder" in c[2] for c in checks if c[0] == BAD):
        print(f"  {step}. SWAP AFFILIATE LINKS: join the programs in")
        print("     docs_content/SAAS_PROGRAMS.md, copy your referral URLs into")
        print("     the 'url' column of data/products.csv (ids listed above).")
        print("     Nothing else in the file needs you.  [~30 min, once]")
        step += 1
    if any(".env missing" in c[1] for c in checks if c[0] == BAD):
        print(f"  {step}. CREATE CONFIG: copy .env.example to .env  [10 sec]")
        step += 1
    if any("credentials" in c[1] for c in checks if c[0] == BAD):
        print(f"  {step}. HUMAN-ONLY ACCOUNT SETUP (only you can do these):")
        print("        a. Instagram app -> switch to Business/Creator account")
        print("        b. Create Facebook Page 'Stack & Save' (category: Science/")
        print("           Tech & Websites > Computers & Technology)")
        print("        c. IG Settings -> Business tools -> Connect the FB Page")
        print("        d. developers.facebook.com -> Create App (type: Business)")
        print("        e. python scripts/setup_tokens.py  (paste explorer token)")
        print("     [~40 min, once]")
        step += 1
    if any("avatar" in c[1] for c in checks if c[0] == BAD):
        print(f"  {step}. RUN: python scripts/make_brand_assets.py  [5 sec]")
        step += 1
    if any("font" in c[1] for c in checks if c[0] == BAD):
        print(f"  {step}. Install a font: drop any .ttf into assets/fonts/  [2 min]")
        step += 1
    if any("ffmpeg" in c[1] for c in checks if c[0] == BAD):
        print(f"  {step}. Install ffmpeg: winget install Gyan.FFmpeg  [5 min]")
        step += 1
    if any("python package" in c[1] for c in checks if c[0] == BAD):
        print(f"  {step}. pip install -r requirements.txt  [1 min]")
        step += 1
    if any("git remote" in c[1] for c in checks if c[0] == BAD):
        print(f"  {step}. GITHUB (enables 24/7 posting with laptop off):")
        print("        a. github.com -> New repository (name: affiliate-engine)")
        print("        b. git remote add origin https://github.com/<you>/affiliate-engine.git")
        print("        c. git push -u origin main")
        print("        d. Repo Settings -> Secrets and variables -> Actions -> New:")
        print("           IG_USER_ID, FB_PAGE_ID, ACCESS_TOKEN, GEMINI_API_KEY,")
        print("           PEXELS_API_KEY  (values from .env)")
        print("        e. Repo Settings -> Pages -> Deploy from branch -> main /docs")
        print("        f. Copy the Pages URL into .env as PUBLIC_MEDIA_BASE_URL")
        print("     [~15 min, once]")
        step += 1

    if warns:
        print(f"\n  Optional upgrades ({len(warns)}) — system runs without these:")
        for _, label, detail in warns:
            print(f"        - {label}: {detail}")

    print("\n  PROFILE COPY (paste when creating accounts):")
    print("    IG/FB name : Stack & Save")
    print(f"    Handle     : {config.BRAND_HANDLE}  (claim on BOTH platforms)")
    print("    IG bio     : The stack that saves you hours. Free trials only.")
    print("                 New tools weekly. Start free below.")
    print("    FB category: type 'software' -> pick 'Software' (any tech category works)")
    print("    Website    : <your GitHub Pages URL from step above>")


def _live_check() -> None:
    try:
        import requests

        r = requests.get(
            f"https://graph.facebook.com/{config.GRAPH_VERSION}/{config.IG_USER_ID}",
            params={"fields": "username,followers_count", "access_token": config.ACCESS_TOKEN},
            timeout=20,
        ).json()
        if "username" in r:
            add(OK, f"live IG token valid: @{r['username']} ({r.get('followers_count')} followers)")
        else:
            add(BAD, "live IG token check failed", str(r))
    except Exception as e:
        add(BAD, "live IG check errored", str(e))


if __name__ == "__main__":
    main()
