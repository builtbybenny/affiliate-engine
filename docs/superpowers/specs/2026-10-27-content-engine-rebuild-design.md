# Content Engine Rebuild — Design

**Date:** 2026-10-27  
**Project:** Stack & Save  
**Status:** Approved by owner for implementation, with stale-content cleanup added 2026-10-27

## Intent and success criteria

Rebuild the copy-generation path so every new post is specific to its featured product, compelling without manufactured urgency or claims, polished in a natural professional voice, and useful enough to merit attention. Apply the same writing and validation standards to every current and future row in `data/products.csv` without hard-coding the current two-product roster.

Keep the existing zero-spend constraint. Improve output quality without promising reach: Instagram distribution is personalized, differs by surface, and cannot be guaranteed by a copy formula. Optimize for an accurate opening, a worthwhile payoff, useful information, and a clear next step; avoid engagement bait and unsupported algorithm folklore.

## Approved scope

Rebuild only the content-generation and copy-quality boundary:

- Product context selection and the instructions sent to Gemini.
- Hook candidates, deterministic selection, factual/style validation, and bounded retry/fallback behavior.
- Caption and slide copy rules, including concise natural copy and supportable claims.
- Existing copywriting/social marketing guidance and focused offline checks for every catalog product.
- Remove stale, unsupported research claims and obsolete generated-copy rules from future output paths. Preserve historical published media/logs and credentials; do not rewrite old posts.

The implementation may replace the current prompt and scoring rules from scratch where they conflict with these requirements. Keep the existing publishing interfaces and behavior intact.

## Non-negotiable invariants

- Do not change `.env`, GitHub secrets, API keys, Meta app settings, scopes/permissions, publisher request shapes, token handling, posting cadence, scheduling, affiliate links, disclosure, or the five-hashtag cap.
- Keep Gemini as the existing optional provider and preserve its current key name, free-tier path, model-fallback mechanism, and graceful template fallback. No paid APIs, new services, subscriptions, or dependencies.
- Preserve the shape consumed by `scripts/generate.py` and media renderers: `hook`, `slides`, `framework`, and `caption` (with existing graceful behavior when AI copy is unavailable).
- Do not publish during implementation or verification. Verify generation offline/dry-run and inspect that publisher interfaces and credential names have not changed.
- Use product data dynamically. Never assume only Systeme.io or beehiiv will be present.

## Content system

### Product context and evidence

Treat an individual product row as the default factual source: name, benefits, specs, price, currency, and trial terms. Pass only relevant context to the model. Research can inform the vocabulary people use and objections to address, but cached facts are not automatically publication-safe: current briefs include facts with weak attribution, old promotions, or little product relevance.

A research fact is eligible for a public claim only when its provenance can be checked (source URL/publication and a usable date, with no stale promotion or unrelated context). Until that provenance is available, do not use the fact as a claim. Never expose internal source notes in captions. If no reliable proof exists, write from the catalog row without inventing numbers or results. Expired cached briefs, old promotional angles, and obsolete hook formulas must be ignored by the generation path and removed or invalidated from active copy inputs; historical published assets remain untouched.

Apply this rule uniformly to existing and newly added products. A missing product-specific proof point is a reason to write a more modest line, not to fill a gap with a model-generated statistic. Product-specific copy must be generated from the row at runtime, not a hard-coded roster or stale product-specific prompt.

### Hook and post structure

Generate a small set of short, meaningfully distinct hook candidates grounded in the selected product, its verified context, and the concept angle. Each opening must be repaid by the post itself. Reject generic competitor-swappable lines, unsupported numbers, manufactured urgency/popularity, false first-person experience, rhetorical bait, and stock AI phrases. Do not optimize by trusting a model's self-assigned score. Use transparent deterministic quality signals and a clear fallback when candidates fail.

Build one argument per post: recognizable reader problem or decision, a concrete and supported product-specific answer, an honest after-state, and one appropriate next step. Avoid feature dumps, keyword stuffing, repetitive templates, fabricated outcomes, and unearned social proof. Keep line rhythm conversational and varied rather than forcing an artificial caption length.

Reels and carousels may share the copy brief but must fit their form: a fast, clear Reel opening and payoff; a carousel cover that makes a truthful promise and interior slides that each earn the next swipe. Keep a single CTA and the existing affiliate disclosure requirements.

### Quality gates and fallback

Use deterministic checks for output shape, product relevance, hook length/readability, duplicate slide lines, prohibited patterns, competitor leakage where currently prohibited, disclosure/caption limits, and claims that introduce numbers or specific outcomes unsupported by approved context. If a draft fails, allow at most one targeted rewrite request; if it still fails or Gemini is unavailable, use product-aware templates that follow the same non-fabrication rules. A fallback must not invent a personal story or product capability either.

Checks should be offline and roster-driven, covering all product rows and failure paths without publishing, calling external services, or mutating real rotation history. Keep existing generation and render interfaces stable.

## Marketing skills

The workspace already vendors the relevant `copywriting` and `social` skills from `coreyhaines31/marketingskills`, and they are present in the skills directory. Do not install a separate paid humanizer, add a dependency, or treat synonym replacement as humanization. Strengthen the existing product-facing quality bar and the relevant existing skill instructions with the approved rules above. Retain source/license provenance and do not refresh/reclone vendored upstream content as part of this task.

## Components and data flow

1. `scripts/generate.py` continues selecting the date, format, product, and concept, then passes the current product plus optional research brief to `core/llm.py`.
2. `core/llm.py` prepares a conservative evidence-aware brief, requests structured copy, chooses/rejects hooks deterministically, validates the complete draft, and returns the stable copy object or `None`.
3. `scripts/generate.py` and `media/carousel.py` / `media/reel.py` continue using the current object and existing template behavior when AI output is absent.
4. Focused local validation exercises all catalog products and mocked model success/failure responses; no live Meta or Gemini call is required.

## Error handling and performance

Network/model failure, malformed JSON, rejected claims, missing research, or missing optional marketing text must not block media generation. Keep retries bounded to one correction attempt and avoid retries whose only goal is hitting arbitrary word-count targets. Preserve existing model failover. Do not add remote dependencies or extra research fetches to the per-post generation hot path. Measure generation call count in verification; do not claim a speedup without comparative timing evidence.

## Verification and acceptance

- Focused offline checks demonstrate valid and failed drafts for every current catalog row and a newly constructed sample row receive the same standards.
- Checks reject examples with fabricated numeric outcomes, fake personal experience, stale/unverifiable research claims, competitor leakage, duplicate/invalid slides, generic hooks, and prohibited AI tells; valid concise evidence-grounded output survives.
- Template fallback remains usable with Gemini absent; dry-run/generation remains non-mutating with respect to rotation state.
- Run the smallest relevant compile and quality checks after final edits.
- Inspect the final diff to confirm no credential, scope, scheduler, publisher, or publishing-interface change.

## Decisions and trade-offs

- Prefer accuracy, clarity, and concrete usefulness over a fixed long-caption SEO target. Natural keyword use is welcome; repetition for a guessed ranking benefit is not.
- Exclude facts from the current cached brief when provenance cannot be verified. This may yield fewer numeric hooks, but is safer and more credible than recycling questionable claims.
- Keep marketing guidance local and zero-cost: the current relevant vendor skills already exist, so install count is not a reason to add a redundant or unverified “humanizer.”
- This work improves the engine's content standards; reach and engagement remain measured outcomes, not guarantees.
