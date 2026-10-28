# Content Engine Rebuild Implementation Plan
> **For agentic workers:** Implement natively in this session, following these tasks in order. Steps use checkbox (`- [ ]`) syntax for tracking.
**Goal:** Make every current and future product post specific, evidence-grounded, polished, and free of invented claims without changing the publishing boundary.
**Architecture:** Keep the existing product planner, optional Gemini model failover, renderer object shape, and publisher integration. Treat product-row data as the trusted fact source, exclude stale/unverifiable cached research, use compact prompts and deterministic copy gates, and retain a truthful product-aware offline fallback.
**Tech Stack:** Existing Python 3, requests, python-dotenv, Gemini free-tier API; stdlib `unittest`/`unittest.mock` for offline quality checks.
**Spec:** `docs/superpowers/specs/2026-10-27-content-engine-rebuild-design.md`

## Global Constraints
- Do not change `.env`, GitHub secrets, API keys, Meta app settings, scopes/permissions, publisher request shapes, token handling, posting cadence, scheduling, affiliate links, disclosure, or the five-hashtag cap.
- Keep Gemini as the existing optional provider and preserve its current key name, free-tier path, model-fallback mechanism, and graceful template fallback. No paid APIs, new services, subscriptions, or dependencies.
- Preserve the copy object shape consumed by `scripts/generate.py` and media renderers: `hook`, `slides`, `framework`, and `caption`.
- Do not publish during implementation or verification. Use offline checks/dry-run only.
- Use product data dynamically. Never assume only Systeme.io or beehiiv will be present.
- Preserve historical published media/logs; invalidate stale active research inputs, not historical posts.

## Review Focus
- Brief absent, malformed, old, or freshly rebuilt without source URL/date → no unsupported fact reaches a public caption.
- New product row with a different name/benefits/trial → same prompt, hook, validation, disclosure, and fallback treatment without code changes.
- Gemini missing, malformed JSON, invalid output, or timeout → generation returns to existing template path without blocking.
- Competitor mentioned in copy → output is scrubbed/rejected without damaging ordinary prose.
- Numeric claims, first-person experience, generic hook, cliché/AI tell, repeated slide, or CTA/disclosure omission → rejected or safely repaired before render.

## File Structure
- Modify `core/briefs.py`: fresh-cache validity and stale-cache fallback behavior.
- Modify `scripts/generate.py`: consume only cached current briefs on the posting hot path; weekly refresh remains intact.
- Modify `data/research_briefs.json`: remove old cached product claims/angles lacking verifiable provenance; preserve valid basic structure for weekly refresh.
- Modify `core/copywriter.py` and `core/concepts.py`: replace fabricated/generic hooks and template fallback copy with dynamic product-row-derived, truthful copy; preserve public call signatures and hashtag/disclosure constraints.
- Modify `core/llm.py`: replace overconstrained prompt, self-scored hook selection, and three word-count retries with compact structured generation, deterministic checks, and at most one quality correction; preserve `write_copy()` signature, Gemini failover, and return shape.
- Modify `skills/marketing/QUALITY_BAR.md`: add engine-specific evidence, voice, hook, and human-edit rules; do not overwrite vendored source skills.
- Create `tests/test_content_quality.py`: offline roster-driven checks and mocked generation paths, including an unseen product row.

### Task 1: Stop stale cached research from reaching copy
**Files:** Modify `core/briefs.py`, `scripts/generate.py`, `data/research_briefs.json`; test `tests/test_content_quality.py`.
**Interfaces:** `briefs.get(product, refresh=True, max_age_days=MAX_AGE_DAYS) -> dict` remains stable; generation uses `refresh=False` and the existing weekly workflow refresh remains unchanged.
- [ ] **Step 1: Write offline tests** for expired/missing-built cache returning `{}`, current cache remaining available only as non-claim context, and generated copy prompt excluding stale `facts`/`angles`.
- [ ] **Step 2: Run `python -m unittest discover -s tests -p 'test_content_quality.py' -v`** and confirm the stale-cache tests fail before implementation.
- [ ] **Step 3: Implement cache validity** so missing/expired timestamps never return stale entries; call `briefs.get(..., refresh=False)` for each post so the publish hot path does not add research fetches.
- [ ] **Step 4: Clear cached claims/angles without source provenance** from `data/research_briefs.json`; retain the JSON `updated`/`products` shape for the weekly refresh job.
- [ ] **Step 5: Rerun the focused tests** and verify the weekly research script still imports and writes the existing brief schema.

### Task 2: Rebuild product-aware copy, hooks, and quality gates
**Files:** Modify `core/llm.py`, `core/copywriter.py`, `core/concepts.py`, `skills/marketing/QUALITY_BAR.md`; test `tests/test_content_quality.py`.
**Interfaces:** Keep `llm.write_copy(product, theme, fallback_hooks, fallback_slides, fallback_caption, brief=None, angle="") -> dict | None`; preserve keys `hook`, `slides`, `framework`, `caption`; keep copywriter public function signatures and existing disclosure/hashtag limits.
- [ ] **Step 1: Add offline tests** for hook determinism independent of model-supplied scores, unique product-grounded hooks, concise captions, current catalog + synthetic future product, disclosure retention, competitor leakage, unsupported digits, first-person claims, AI-tell phrases, duplicate slides, malformed model JSON, and no-key fallback.
- [ ] **Step 2: Run `python -m unittest discover -s tests -p 'test_content_quality.py' -v`** and confirm the relevant failure cases fail before implementation.
- [ ] **Step 3: Replace generic/fabricated hook banks** with truthful product-row-driven hook selection; replace the fallback caption's rotating engagement-bait CTAs with one direct, disclosure-safe action.
- [ ] **Step 4: Replace `SYSTEM_BRIEF` and `write_copy()` prompt** with one concise argument, natural keywords, no personal experience/popularity claims, supported product facts only, platform-appropriate opening/payoff, and structured JSON without a fixed long-word floor or self-rated scores.
- [ ] **Step 5: Add deterministic draft checks** for shape, short readable hook, product relevance, duplicate slides, unsupported digits, competitor references, stock AI patterns, one CTA, caption limit, and required affiliate disclosure; allow one targeted correction, then return `None` for the existing safe fallback.
- [ ] **Step 6: Update `QUALITY_BAR.md`** with the same facts-first human editing rules, explicitly separating vividness from invented proof and forbidding synonym-only “humanization.”
- [ ] **Step 7: Rerun the task tests** and inspect sample outputs for both current products and a synthetic future product.

### Task 3: Verify generated content and protected interfaces
**Files:** No additional source changes unless a focused failure requires repair.
- [ ] Run `python -m compileall -q core scripts media publishers`.
- [ ] Run `python -m unittest discover -s tests -p 'test_content_quality.py' -v` from a clean post-edit state.
- [ ] Run `python scripts/generate.py --today --dry-run`; confirm it reports product-specific planning without changing `data/concept_history.json`, creating media, or publishing.
- [ ] Compare `git diff -- .env publishers/instagram.py publishers/facebook.py .github/workflows/scheduler.yml .github/workflows/weekly-evolve.yml`; confirm no diff in credentials, permissions, publisher APIs, schedule, or workflows.
- [ ] Inspect `git status`/diff and confirm no published historical files were modified, stale active brief claims are removed, and no dependencies were added.

## Refinements shipped 2026-10-28

Second pass over the same boundary, after reading every published caption and running live drafts. Credentials, keys, scheduling, publishers, cadence, disclosure text and the five-hashtag cap are untouched.

1. **Anti-repetition memory.** `copywriter.recent_hooks(product)` reads the opening line of this product's most recent published captions back from the committed Pages archive (`docs/media`). Two products at 2 posts/day means each product opens ~12 posts a month, and the previous deterministic template hook shipped one identical sentence forever. No new state file, no extra CI commit, no network; a product added tomorrow builds this memory from its first post. The recent list is both injected into the prompt (do not reuse) and enforced by a gate.
2. **Fallback copy rebuilt for quality and variety.** Hooks are assembled from real catalog details × three truthful framings, biased toward details that carry a number or plan term, seeded by date and concept, skipping recent openings. The robotic `Listed trial terms: …` label is gone; the trial line now reads as a sentence.
3. **Coherence rule.** The shipped hook is the sentence the caption actually opens with (`_first_sentence`). Earlier code let the model nominate one hook and code pick another, so the on-screen line and caption line 1 disagreed. Alternate candidates are still requested and used when the opener fails a gate; a single-paragraph caption is never rewritten.
4. **Precision fixes in the numeric gate.** Claims are compared by value, so a catalog `2500` accepts `2,500` while `10,000` still fails. The gate also now requires the featured product to be named (or a distinctive catalog detail), exactly one action, no engagement bait, and a caption body beyond the opening line.
5. **Repairs instead of rejections.** A slide that echoes the hook, repeats another slide, or carries the CTA is dropped deterministically; the renderer already ships its own CTA slide/outro. Model-written disclosure wording is stripped before the canonical sentence is appended, so a caption can no longer carry two disclosures.
6. **Form-aware prompt.** Reels get first-frame-legible, three-line guidance; carousels get cover-promise, swipe-earning guidance. Optional `format_name=` kwarg keeps `write_copy()` backward compatible.
7. **Model fallback ordered by writing quality.** Live probe: the newest model returns HTTP 503 under free-tier load, and the old order put the lite model second, so every 503 silently downgraded all captions in that run. Full models now sit above lite and the retired `gemini-2.5-flash` name (HTTP 404) is gone. Failover mechanics are unchanged.
8. **Checks.** `tests/test_content_quality.py` grew from 10 to 20 offline tests covering all of the above plus a sparse future-product row; `compileall`, both dry-run formats, live drafts for both products, and a carousel + reel render were run against shipped code. The reel render needs its network stock-footage step stubbed locally; that dependency and its behaviour are unchanged.
