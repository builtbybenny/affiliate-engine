# 🧲 Lead-Magnet Playbook (comment-keyword → DM)

The mechanic: a listicle carousel ("12 free AI apps that feel illegal to
know") ends with `COMMENT "AI"` — commenters get the full list. Comments
explode (each one is public social proof), the algorithm reads a busy
comment section as quality, and every commenter is a DM contact you can
nurture. This is the growth loop paid tools like ManyChat sell — built here
on Meta's official APIs for $0.

## What's already built

| Piece | File |
|---|---|
| Two curated lists (real, live, free) | `data/lead_lists.json` — edit freely |
| Listicle carousel renderer + keyword CTA slides | `media/lead.py` |
| Reply bot (comment scan → DM or public reply, dedupe log) | `scripts/reply_bot.py` |
| 24/7 server loop (30-min poller) | `.github/workflows/keyword-dm.yml` |
| Public "Lists" page for the impatient | `scripts/build_lists_page.py` → `public/lists.html` |

## Phase 1 — works on day 1, zero App Review

1. Generate a lead post: (command below in Using it)
2. The bot scans comments every 30 min, **likes** each keyword comment and
   **replies publicly**: "@user sent you the list — check your DMs!" with the
   bio link doing the actual delivery.
3. Public replies still notify the commenter, still look personal, and add
   to the comment count. Conversion is nearly as good as DMs.

## Phase 2 — auto-DM (one-time free App Review)

Meta requires Advanced Access for `instagram_manage_messages` +
`instagram_manage_comments` before your app can DM non-role accounts.

Runbook (one evening):
1. developers.facebook.com → your app → App Review → Requests
2. Add `instagram_manage_messages` and `instagram_manage_comments`
3. For each: use case text = "We operate a SaaS-tools recommendation page.
   Followers comment a keyword on our posts requesting our free tools list;
   we send the requested list by DM and reply to the comment. Permission is
   used solely to respond to users who explicitly commented."
4. Screencast (phone screen-record, 60-90s): show a post, comment the
   keyword, show the bot replying/serving the list. Meta wants to see the
   exact loop.
5. Business verification: Settings → Business Verification (upload trade
   license / GST cert / incorporation doc — India accepted).
6. Submit; approval historically takes 3-10 days.
7. Until approved, Phase 1 runs automatically (the bot degrades itself).

Compliance notes (keep the app alive):
- Only ever message users who commented first (this bot does exactly that)
- Include an opt-out line ("reply STOP and I won't message again") in the
  list message if you start batching follow-ups
- Don't DM links that differ from the public list — Meta flags bait-and-switch

## Using it

```bash
# make a lead carousel (pick list id from lead_lists.json)
python -c "from media.lead import build_lead_carousel; build_lead_carousel('free_ai_apps')"
python -c "from media.lead import build_lead_carousel; build_lead_carousel('github_repos')"

# preview what the bot would do
python scripts/reply_bot.py --all --dry-run

# publish it (same as any post)
python scripts/publish.py --today --format carousel --ig-only
```

## Cadence that works

- 1 lead post per week (Friday or Saturday — casual scroll time)
- Rotate lists; refresh each list monthly (drop dead links, add new tools)
- Pin the best-performing lead post to the profile
- Every new follower from a lead post sees your product carousels next —
  that's the funnel: give value first, monetize the trust.
