# ♻️ How the Engine Evolves Itself

The goal: never stale, always fresh concepts, every product gets enough
repetition to convert casual scrollers — with zero daily human input.

## 1. Freshness — the concept×product matrix

Every post is a **pairing**: (concept, product, format). The engine tracks
every pairing it has ever made in `data/concept_history.json` and:

- **Never repeats a pairing** while unused ones exist. 10 concepts × 8
  products × 2 formats = ~120+ unique combinations before anything recycles.
- Concepts are angles (Stack Drop, Honest Versus, Hidden Feature, Day in
  the Life, Price Transparency, The Mistake, Myth Crusher...), not
  templates. Same tool, different story every time it appears.
- The weekly calendar sets the rhythm (which format each day), the concept
  engine chooses the *story*.

## 2. The repeat-exposure weave (casual scrollers)

Scrollers need to see a tool ~3-7 times before clicking. But blunt repetition
kills the feed. So:

- `planner.pick_product_lru()` always features the **least-recently-shown**
  product — the whole catalog cycles before anything repeats.
- If a product IS picked again within 21 days, the engine **reframes
  honestly**: it switches to rerun concepts ("Back by Demand",
  "Social Proof Drop") that say "you keep asking, here it is again" —
  repetition with a reason, which reads as momentum, not spam.
- Lead-magnet posts (comment-keyword) carry the weekly affiliate pick in
  the caption AND the DM — the softest, most honest retouch there is.

## 3. The trend radar (continuous market exposure)

Every Sunday (GitHub Actions, free): `scripts/radar.py` pulls

- Product Hunt feed (launches)
- TechCrunch apps
- VentureBeat AI
- Hacker News front page

Scores items for SaaS-affiliate signal ("ai", "free", "automation",
"productivity"...), filters noise (crypto, celebrity...), and writes:

- `data/radar_candidates.json` — rolling 100-best, deduped
- `data/radar_digest_YYYY-Www.md` — ranked table + 5-minute Sunday ritual

Your only creative job: skim the digest, add 1-2 winners to
`data/products.csv` with your referral link, prune dead ones. The engine
handles everything else — they enter the LRU rotation and the concept
matrix immediately.

## 4. What staleness looks like now

| Mechanism | Failure it prevents |
|---|---|
| Concept matrix | "Same post again" fatigue |
| LRU product selection | Over-promoting one tool, starving the rest |
| Honest rerun framing | Repeating without looking desperate |
| Trend radar | Promoting dead tools, missing new launches |
| Weekly digest + ritual | You = strategist (10 min/wk), engine = labor |

## 5. Optional human upgrades (from TOOLKIT.md)

- Fonts + music → instant production-value lift
- Gemini key → per-post AI copy in brand voice
- Pexels key (free) → real stock imagery behind slides (planned hook exists)
- Screen recordings → the highest-converting reel format
