# ⚙️ Daily Workflow — how posting works (no manual steps)

**One line:** nobody checks or pushes anything to publish. GitHub runs the whole
loop automatically. Updated 2026-10-02 (ramp mode).

## Every day (ramp: 1 post/day until ~Oct 15)

| When (US Eastern) | What happens |
|---|---|
| 7:09 / 7:27 / 7:46 / 7:57 PM | GitHub's clock tries to start the post job 4 times (it always wakes a few minutes late — that only adds randomness) |
| First attempt | Job asks *"already posted today?"* by reading `data/published_log.csv`. Yes → stops instantly (a quick green run) |
| If not posted yet | Random draw decides: 35% chance now, then 55%, then 70%, last try forces it — plus a random 0–3 min wait. Result: **exactly one post, at a different time each day** |
| ~3–6 min of work | Picks product + concept from the calendar → writes caption (AI) → renders reel (stock + gradients, ffmpeg) → pushes media to GitHub Pages → waits until the public URL serves it → **posts to Instagram + Facebook** → appends the log row and pushes it so tonight's later tries can see it and skip |

Why randomized times: posting at a fixed rounded time every day is a bot signal.
Four odd-minute triggers + dice + GitHub's own lag = no two days look alike.

## Your routine (the human part)

- **Daily:** nothing required — optionally glance at the post.
- **If a run breaks:** you get a failure email from GitHub → type `continue` in a
  thread and Buffy diagnoses and fixes it.
- **Occasional `continue`:** yesterday's run gets verified green, account health
  checked, next pending task done.
- **Affiliate links ready:** paste them in the thread — swapped into
  `data/products.csv` and pushed; the link-in-bio page rebuilds itself.
- **~Oct 15 ramp check:** re-enable the 12:30 UTC carousel morning slot → back to
  2 posts/day (see `data/_state.json` → `pending_next_session`).

## What runs on a schedule besides the post

| Workflow | When | What |
|---|---|---|
| `scheduler` | daily, evening window above | the post (reel now, carousel after ramp) |
| `weekly-evolve` | Sunday 03:00 UTC | trend radar scan → commits digest to `data/` |
| `keyword-dm` | hourly (bot switch OFF) | comment-keyword replies — stays off until token has comment permission |
| `refresh-link-bio` | on push touching `data/products.csv` / `data/hashtags.txt` | rebuilds + commits the link-in-bio page |

## What does NOT run during the ramp

- **Carousels** — parked until ~Oct 15 (manual one-off via *Run workflow* is possible;
  note it uses that day's single post slot).
- **Reply bot** — kill switch off (backlog).

## Failure playbook (short version)

1. Red run → download logs (Actions API needs admin auth; the stored git
   credential works, never print it).
2. Most common breakages: ffmpeg missing on runner (fixed), Pages not serving
   media yet (wait step retries 20×), Meta token/scope issues → crisis playbook
   in `data/_state.json` → `technical_learnings`.
3. If a post failed before the log row was written, the next trigger the same
   evening retries automatically — that's built in.
