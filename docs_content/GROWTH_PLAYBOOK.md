# 📈 30-Day Growth Playbook (no ad spend)

**Assumption:** 1 carousel + 1 reel per day, 6–7 reels/wk is the growth engine.
Track everything with `python scripts/insights.py`.

## Week 1 — Foundation
- Post 1×/day minimum; same visual style (engine handles it).
- Bio: "The stack that saves you hours. Free trials only. Start free below." + Pages URL.
  (SaaS edition: see SAAS_GROWTH_PLAYBOOK.md for the full funnel.)
- Reply to **every** comment within an hour (algorithm rewards early engagement).
- Hashtags: keep engine defaults; note which posts surface in `#small` tags.

## Week 2 — Hooks & formats
- Watch retention: if reels die <3s, the hook slide/hook line is weak —
  edit `HOOKS` in `core/copywriter.py` (shorter, more curiosity, more numbers).
- Test trial reels (engine supports `trial` reels via API later) to test
  hooks on non-followers without polluting your grid.

## Week 3 — Engagement loops
- End carousels with a question slide ("Which one are you buying?").
- Story-resurface: manually share each post to Stories (30 s/day).
- Collab DMs: 3 micro-creators in your niche/week — shoutout exchanges.

## Week 4 — Double down
- Re-render top-3 posts as new variants (change seed/hook, keep product).
- Start collecting DM keywords ("send DM word 'LAMP'") — builds a manual list.
- Add the 2 best-converting products to the bio page top.

## KPIs to check weekly (scripts/insights.py)
| Metric | Healthy | Action if low |
|---|---|---|
| Reel avg watch % | >50% | Shorten to 7–10s, stronger first frame |
| Carousel saves/post | >1.5% of reach | Better slide-1 hook, more "list" content |
| Followers/wk | +2–5% | Post reels at audience timezone peak |
| Link clicks (bio) | ≥0.5% of reach | Stronger CTA slide, fewer link distractions |

## Scale-up options later (still $0)
- Second niche account once #1 hits ~3k followers.
- Auto-comment moderation via Graph API (already in your permissions).
- UGC-style real product photos beat stock — order one product, shoot 5 pics.
