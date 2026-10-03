# 🧰 TOOLKIT — what to install or hand me, and exactly why

You offered real tooling instead of workarounds. Accepted. Below is the full
wishlist, ranked by impact. Everything is free. Each item says what it is,
where to get it, and what it unlocks in the engine.

## 1. Typefaces (biggest visual upgrade, 5 minutes)

The slides currently render in Arial Bold (system fallback). Professional
affiliate pages use a 3-weight family. Get the free Inter family:

- Download: https://github.com/rsms/inter/releases (Inter-4.x.zip)
- Unzip, then copy exactly these three files into `assets/fonts/`:
  - `Inter-Black.ttf`   → headline weight (hook slides get punchier)
  - `Inter-Bold.ttf`    → body/benefit slides
  - `Inter-Regular.ttf` → fine print, captions on slides
- The engine auto-detects them by name — no config change. Rerun
  `python scripts/generate.py --today` to see the difference.
- Alternative with same effect: Montserrat (fonts.google.com) — engine
  also auto-detects Montserrat-Black/Bold/Regular.

## 2. Music beds for reels (10 minutes) — now MOOD-MATCHED

Silent reels underperform. The engine now picks tracks to match the
content: calm for how-tos and transformations, upbeat for deals and free-
tool rundowns, corporate for stack/comparison posts. It does this by
filename — name your tracks like this when you drop them into
`assets/music/`:

- `calm-01.mp3`, `calm-02.mp3` → how-to / before-after reels
- `upbeat-01.mp3` → deal alerts / free-tool roundups
- `corporate-01.mp3` → stacks, comparisons, myth-vs-fact

Start with just two (one `calm`, one `upbeat`) — that covers everything
at launch. Add more anytime; the engine picks randomly within the right
mood so followers don't hear the same bed every reel. No mood-named file
for a theme? It falls back to any track. Empty folder? Silent reels, as now.

Where to get free, no-attribution tracks: Pixabay Music (pixabay.com/music)
or the YouTube Audio Library (studio.youtube.com → Audio Library).

The engine also fades music in/out on every reel automatically.

## 3. AI copywriting — ✅ DONE (key received & verified live)

Your Gemini key is installed in `.env` and tested working (Sept 2026).
Hooks, slide text and captions are now AI-written in the brand voice.
The engine auto-switches between Gemini models when Google retires one
or when free-tier demand spikes — you never need to touch it.

One small thing left for YOU (during Stage 6, GitHub setup): add the same
key as a repo secret named `GEMINI_API_KEY` so the cloud scheduler uses
AI copy too. 30 seconds, instructions appear in doctor.py output.

## 4. Screen recorder for tool demos (5 minutes, when you're ready)

Biggest conversion unlock for SaaS reels (real product UI in first 8s):

- OBS Studio: https://obsproject.com (free, Windows/macOS/Linux)
- Settings → Video: Base 2560x1440 or 1920x1080; MP4 output
- Record ~60s per tool, save as `data/screen_recordings/<id>.mp4`
  (ids: gohighlevel, systeme, beehiiv, pictory, framer)
- Windows alternative already installed: Win+G (Xbox Game Bar).

## 5. Product visuals (10 minutes)

Tool screenshots for carousel covers: save as `data/product_images/<id>.jpg`.
Sources: each tool's press/brand page (official logos + product shots),
or take your own screenshots once OBS is in.

## 6. Stock photography — ✅ DONE (key received & verified live)

Your Pexels key is installed and tested. Slides and reels now automatically
fetch relevant license-free photos (designer desks, creators, workspaces)
as backgrounds, matched to each product's vibe. Photos are downloaded once
and cached forever in `data/stock/` — no repeated downloads, no cost.
Add it as GitHub secret `PEXELS_API_KEY` during Stage 6 too.
- Nothing else needed. The trend radar (Product Hunt / TechCrunch /
  VentureBeat / Hacker News) already runs on free RSS — no keys, no limits.

## 7. Already installed (no action needed)

- ffmpeg 9.0.1 — reel rendering ✓
- Python 3.14 + all packages ✓
- Git — you have it (you use GitHub already) ✓

## Priority order

1 → 2 (fonts, music) take ~15 minutes and upgrade literally every post
the engine will ever produce. 3 and 6 are already done — only their
GitHub-secret steps remain, and doctor.py will remind you.
4 → 5 come after go-live, tool by tool, at your Sunday ritual.
