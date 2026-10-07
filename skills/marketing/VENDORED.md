# Vendored marketing skills

Subset of https://github.com/coreyhaines31/marketingskills (MIT License,
Copyright (c) 2025 Corey Haines — full text in the source repo LICENSE).

- **Pinned at commit:** `f719a8079c694e3267d47b6b60a62aa926055f2c`
- **Vendored:** 2026-10-07 by session 9d
- **Versions:** copywriting 2.1.0, social 2.3.2, offers 1.0.1, lead-magnets 2.0.0

## Why these four
The engine's funnel is reel/carousel → caption → keyword comment → DM list →
bio link → affiliate signup. `copywriting` (caption quality, anti-AI-slop),
`social` (Reels hooks + IG mechanics), `offers` + `lead-magnets` (the DM list
copy closest to revenue). The other ~46 catalog skills target channels we do
not operate (email lists, paid ads, popups, PR...) — see INDEX.md for the
full menu with trigger rules for staged pulls.

## What was dropped from the copied folders (and why)
- `*/evals/` — vendor-internal eval fixtures, not guidance.
- social: `listening*.md`, `x-algorithm.md`, `reverse-engineering.md`,
  `carousel-frameworks.md` — X/listening-specific; IG carousel guidance
  already lives in our `media/carousel.py` + `post-templates.md`.
- offers: bonus-stacking/guarantee/scarcity/value-equation/examples —
  we promote other people's SaaS offers; `saas-offers.md` + `offer-anatomy.md`
  carry the applicable framing (banned vocabulary included via SKILL.md).
- lead-magnets: `benchmarks.md` — numeric benchmarks need a mail list we
  don't run yet.

## Runtime contract
- `skills/marketing/QUALITY_BAR.md` — compact prompt block, prepended to the
  caption/hook generation prompt in `core/llm.write_copy` (graceful skip if
  the file is missing so caption generation never dies on a vendored file).
- `data/marketing_quickref.md` — regenerated distillate (human reference,
  not injected into prompts).
- `skills/marketing/INDEX.md` — full 70-skill menu + trigger rules.

## Refresh protocol (monthly)
1. `python scripts/marketing_distill.py --refresh` — re-clones the pinned
   repo, reports drift, re-syncs the subset, rebuilds INDEX.md + quickref.
2. Re-read QUALITY_BAR.md against any changed vendor text; hand-edit it.
3. Bump the pinned SHA + versions in this file.
