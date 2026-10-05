# Retention Playbook — Stack & Save (2026-10-05 research pass)

Why this exists: the account is showing a ~100% skip rate on early reels.
Too little data to panic about (single-digit impressions), but every fix in
here is cheap and correct regardless of sample size, so we optimized now.

Sources: Retensis skip-rate benchmarks 2026, TrueFuture Media skip-rate
guide (cites Mosseri/Instagram official hooks advice), Shortzly
short-form retention guide 2026, Outfame Instagram SEO 2026 guide
(cites Mosseri on search keywords).

## The benchmarks (Reels, 2026)

Skip rate = viewers who swipe away in the first 3 seconds. It is measured
in the IG app: Reel → ⋯ → View insights → "Skipped".

| Skip rate (first 3s) | Rating |
|---|---|
| Below 15% | Exceptional |
| 15–20% | Strong |
| 20–30% | Healthy |
| 30–40% | Needs work |
| Above 40% | Problem — first frame isn't compelling |

Educational/product Reels start harder than entertainment: viewers spend
the opening seconds deciding if the topic applies to them. Judge ourselves
against our own last 10–20 comparable Reels, not against meme pages.

Skip rate is a **gating function**: if everyone skips, the reel never
accumulates the watch time and engagement data Instagram needs to push it
to Explore. Fixing the opening is upstream of every other metric.

## What lowers skip rate (consensus across sources)

1. **First frame works sound-off.** Freeze frame 1, mute, shrink to phone
   size: can you tell what it's about and what's in it for you? If not,
   no caption rescues it.
2. **Hook = a promise, not an intro.** Hard claim with a number/cost,
   under 10 words, on screen at frame 0. Banned: logo animation, brand
   intro, "hey guys", slow establishing shots, rhetorical questions.
3. **Product in use, not a logo.** Opening with the product *doing the
   thing* reads as creator content; brand intros read as ads.
4. **One promise per reel.** Narrower is easier to understand and deliver.
5. **Truthful preview.** Clickbait (mystery without meaning) gets the
   skip *and* the drop-off. "This loose neutral caused the flickering
   lights" beats "you won't believe what we found".
6. **Then the investment window (3–15s).** Confirm the promise fast,
   no padding, no recap. 12–15s on one static frame = scroll; change the
   visual when the information changes.
7. **Loop/close with intent.** A close that calls back to the opening
   invites a replay — replays are the strongest per-impression signal.

## Caption SEO (Instagram search + Google)

- **Primary keyword in line 1** — Instagram scans captions for search;
  line 1 is read before "more". Mosseri: "the keywords someone uses in
  the search bar is the most important factor."
- Keyword repeated naturally 2–3 more times; no stuffing (confuses the
  ranking model).
- **3–5 hashtags**, relevant, camelCase (#SaasTools). We run 5 folded
  into the caption (+ #ad in the disclosure line).
- **On-screen text is read by IG's AI** — keyword phrases in slide text
  help ranking too (our slides now carry them).
- One **specific** engagement question in the caption drives comments;
  comments contextualize the post for ranking.
- Alt text and profile name field matter for discovery (profile-level,
  not per-post — separate task).

## What we changed in the engine (2026-10-05)

- **Hook bank dumped** (`data/hook_library.json` deleted, hook_research.py
  retired). Every post now gets 4 AI-written hook candidates seeded from a
  per-product research brief, scored for retention by
  `llm.pick_retention_hook()` (digits +15, ≤8 words +10, statement +5,
  punch-gate hard filter).
- **Research briefs** (`core/briefs.py`): Google News + marketing-blog
  articles harvested per product, distilled by Gemini into
  `data/research_briefs.json` — real search keywords, attributable facts,
  buyer objections, pain-led angles. Refreshed weekly in CI + lazily when
  stale; stale/empty briefs never block posting.
- **Detailed SEO captions**: 170–240 words, keyword in line 1, 2 cited
  facts with sources, one objection answered, one specific engagement
  question, CTA + disclosure. Capped under 2,000 chars so the folded
  hashtag block still fits IG's 2,200 limit.
- **Reel scene 1 = the hook**, big in center, fading in within 0.3s;
  benefits start before 2s (old structure spent 2.8s on the product name).
  Product name still rides the accent chip on every frame + outro card.
- Brightness/chroma lift + thinner scrims (measured mean luminance
  77.6 → 115.3) — a dim first frame was part of the skip problem.

## Measurement gaps (fix when convenient)

- **Skip rate is only readable in the IG app right now.** The Graph API
  needs the `instagram_manage_insights` scope, which our token lacks —
  re-run `scripts/setup_tokens.py` with that scope added and we can pull
  per-reel skip rate / watch time programmatically.
- Same story for `instagram_manage_comments` (first-comment hashtags).
- Compare like with like: only benchmark tonight's reel against reels of
  similar length/format (median of last 10–20), change one variable at a
  time (tonight's variable: hook + brightness together is deliberate —
  both were failures, not experiments).
