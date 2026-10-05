# 🔗 Affiliate Engine — Instagram + Facebook, zero budget, zero subscriptions

> **▶ START HERE:** open **SETUP_GUIDE.pdf** (project root) — a field-by-field,
> zero-guessing runbook for every manual step: IG account, FB Page, linking,
> Meta developer app, token, GitHub. Then run `python scripts/doctor.py`
> after each stage to see what's left.

A complete, free system that plans, designs, renders and posts affiliate content
to **Instagram** (carousels + reels) and **Facebook** (photos/videos) —
with **no editing skills required** and **no paid tools**.

```
data/products.csv ──► planner ──► copywriter ──► carousel (Pillow)
      │                              └──────────► reel (Pillow + ffmpeg)
      │
      └──► build_link_page ──► GitHub Pages (link-in-bio)
                     │
     publish ──► Instagram Graph API + Facebook Page API
                     ▲
     GitHub Actions (cron) or scripts/scheduler_local.py — the automation
```

## What you get

| Piece | File | What it does |
|---|---|---|
| Content calendar | `core/config.py` | Mon–Sun themes: how-to, top picks, deal alert… |
| Product rotation | `core/planner.py` | No repeats until every product has been featured |
| Copy engine | `core/copywriter.py` | Hooks, captions, hashtags — template based, editable |
| Carousel factory | `media/carousel.py` | Branded 1080×1350 slides with product image, dots, CTA |
| Reel factory | `media/reel.py` | 1080×1920 MP4: Ken Burns motion, animated captions |
| IG publisher | `publishers/instagram.py` | Official Graph API: images, carousels, reels |
| FB publisher | `publishers/facebook.py` | Page photos, videos, link posts |
| Link-in-bio | `scripts/build_link_page.py` | Free GitHub Pages page with your affiliate links |
| Insights | `scripts/insights.py` | Followers, per-post likes/comments, best post |
| Scheduler | `.github/workflows/scheduler.yml` | Posts twice a day, unattended, free |

## Setup (one evening, ~45 min)

### 0. Run the doctor first
```bash
python scripts/doctor.py
```
It audits the whole system and prints **your exact remaining manual steps**
(in order, with time estimates) plus copy-paste profile text for the
@stackandsavehq accounts. Rerun it after each step until it says
`ALL CRITICAL CHECKS PASS`. Use `--live` to also verify your Meta token.

### 0.5 Prerequisites
- Python 3.11+ and ffmpeg (`winget install Gyan.FFmpeg` / `brew install ffmpeg` / `apt install ffmpeg`)
- A **Facebook Page** + an **Instagram professional** (Business/Creator) account **linked to that Page**
  (Instagram app → Settings → Business tools → Connect a Facebook Page)
- A free GitHub account (hosting + scheduling)

### 1. Clone & install
```bash
pip install -r requirements.txt
copy .env.example .env        # then edit BRAND_NAME, BRAND_HANDLE, NICHE
```

### 2. Connect your accounts (free, official)
```bash
python scripts/setup_tokens.py
```
Paste a short-lived token from developers.facebook.com/tools/explorer
(permissions: `pages_show_list, pages_read_engagement, instagram_basic,
instagram_content_publish, pages_manage_posts, instagram_manage_comments,
business_management`). The wizard writes a
**never-expiring Page token** into `.env` and resolves your IDs.

### 3. Add your affiliate products
Edit `data/products.csv`: name, benefits (pipe-separated), specs, price, and
your **affiliate URL**. Drop product photos into `data/product_images/`
(named `<id>.jpg`) — the carousel cover and reel use them automatically.

### 4. Generate + publish (first run)
```bash
python scripts/generate.py --today          # media lands in public/media/
python scripts/publish.py --today --dry-run # shows the public URLs it will use
python scripts/publish.py --today           # posts to IG + FB
```

### 5. Go full-auto (no computer left on)
1. Push this repo to GitHub (private is fine).
2. Repo → Settings → Secrets → Actions → add `IG_USER_ID`, `FB_PAGE_ID`, `ACCESS_TOKEN` (paste from `.env`).
3. Repo → Settings → Pages → Deploy from branch → `main` / `/docs`.
4. Add the secrets `BRAND_NAME`, `BRAND_HANDLE` too (or edit values in the workflow).
5. Workflows `scheduler.yml` (posts 11:00 + 18:30 IST) and
   `refresh-link-bio.yml` (rebuilds bio page when products change) run unattended.
6. Put your Pages URL (`https://<user>.github.io/<repo>/`) in both bios.

Prefer your PC? `python scripts/scheduler_local.py` does the same locally.

### 6. Weekly ritual (15 min, Sunday)
```bash
python scripts/insights.py
```
- Double down on formats that win, swap losing hashtags in `data/hashtags.txt`.
- Add 2–3 fresh products; prune dead links from `products.csv`.

## Compliance (keep your accounts safe)
- Every caption ends with the plain-English affiliate disclosure (commission note).
- Use `rel="nofollow sponsored"` on bio links (already in the bio page builder).
- Never spam links in comments; keep them in bio/DMs.
- Follow each network's affiliate program terms (Amazon Associates requires
  link disclosure and doesn't allow link cloaking).

## Costs
| Item | Cost |
|---|---|
| Media rendering (Pillow + ffmpeg) | ₹0 / $0 |
| Meta Graph API publishing | ₹0 / $0 |
| Hosting (GitHub Pages) + scheduling (GitHub Actions) | ₹0 / $0 |
| Link-in-bio page | ₹0 / $0 |
| Scheduling/Buffer/Hootsuite/etc | **not needed** |
