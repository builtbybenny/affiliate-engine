"""Copy engine: hooks, captions, hashtags, slide text.

Pure templates — deterministic, free, and editable by anyone. Improve your
copy by editing data/hashtags.txt or the template lists below.
"""
from __future__ import annotations

import random
import re
from datetime import date

from core import config, planner

# Hooks are generated from each product row at runtime. Keeping an empty
# legacy mapping prevents older imports from breaking while ensuring retired
# fixed hooks cannot enter a future post.
HOOKS: dict[str, list[str]] = {}

# Plain-English FTC disclosure (user decision 2026-10-05): a full sentence
# beats a #ad hashtag — clearer to readers, still satisfies affiliate-program
# terms (the word "affiliate" is right there). Caption shows 5 hashtags now.
DISCLOSURE = "Affiliate link — we may earn a small commission at no extra cost to you."

# Fallback hashtag pool if data/hashtags.txt is missing (SaaS/tech).
DEFAULT_HASHTAGS = [
    "saas", "saastools", "aitools", "techstack", "productivitytools",
    "solopreneur", "smallbusinesstools", "startuplife", "buildinpublic",
    "nocode", "automation", "marketingtools", "freelancetools",
    "aisaas", "foundertips", "toolstack",
    "workflowautomation", "digitaltools", "reels", "explorepage", "instabusiness",
]


def load_hashtags() -> list[str]:
    if config.HASHTAGS_TXT.exists():
        tags = [
            t.strip().lstrip("#")
            for t in config.HASHTAGS_TXT.read_text(encoding="utf-8").splitlines()
            if t.strip()
        ]
        if tags:
            return tags
    return DEFAULT_HASHTAGS


# ── Featured-tag rotation (user decision 2026-10-25) ────────────────────────
# Twice a week for one month a high-reach fyp-family tag is swapped INTO the
# five-tag block, replacing the block's LEAST important tag (the last, random
# pool tag) so the total stays at Instagram's hard cap of 5. Rest days keep
# the ordinary 5 relevant tags, untouched.
#
# Tag pool taken from iqhashtags.com/hashtags/hashtag/fyppppppppppppppppppppppp
# ("10+ Trending Tags for Instagram Reels", Oct 2026): the fyp family plus its
# listed related tags. Generic non-fyp tags from that page (#viral, #trending,
# #explore) are deliberately NOT used — they are off-niche for this account.
FEATURED_TAGS = ["fyp", "fypシ", "fypage", "fypp", "fy", "foryou", "foryoupage"]
FEATURED_WEEKDAYS = (2, 5)          # Tuesday + Friday = twice a week
FEATURED_FROM = date(2026, 10, 26)  # start of the next full posting week
FEATURED_UNTIL = date(2026, 11, 22) # one month of cadence, then re-ratify


def featured_tag(for_date: date | None = None) -> str:
    """'#fyp' family tag for today, or '' on rest days / outside the window."""
    d = for_date or config.now_local().date()
    if not FEATURED_FROM <= d <= FEATURED_UNTIL:
        return ""
    iso = d.isocalendar()
    if iso.weekday not in FEATURED_WEEKDAYS:
        return ""
    # Rotate by week + weekday so consecutive featured posts differ.
    return FEATURED_TAGS[(iso.week * 2 + iso.weekday) % len(FEATURED_TAGS)]


_BANNED_HOOK_WORDS = (
    "supercharge", "unlock", "game-chang", "seamless", "next level",
    "take it to the next", "elevate", "revolutioni", "nobody talks",
    "secret", "hidden feature", "everyone is", "most requested",
)


def hook_coherent(hook: str, product: dict, from_ai: bool = False) -> bool:
    """The hook belongs to THIS product's post — 2026-10-12 gate.

    Failure seen live: Gemini wrote 'Mailchimp bills just doubled your
    creator revenue' as the hook of a *beehiiv* slide — grammatically
    fine, punch gate passed, but it named the competitor as the subject
    of a false claim. The punch gate measures style; this measures
    subject. Rules:
      • AI hooks never name the competitor (prompt even bans it; this
        enforces it — belt and braces).
      • Curated concept templates keep their versus formats
        ("{name} vs {alt}") — they're designed and reviewed.
    """
    line = (hook or "").strip().lower()
    if not line:
        return False
    alt = (product.get("alt") or "").strip().lower()
    if alt and alt in line:
        return not from_ai
    return True


def punchy(line: str) -> bool:
    """Quality gate for hook lines (2026-10-05 content review).

    A hook must be a statement that lands: not a soft question, not hype
    filler, not a run-on. Failing hooks fall back to the concept bank.
    """
    line = (line or "").strip()
    if not line or len(line.split()) > 14:
        return False
    if line.endswith("?"):
        return False
    low = line.lower()
    return not any(w in low for w in _BANNED_HOOK_WORDS)


# ── Anti-repetition memory (2026-10-27) ────────────────────────────────────
# Two products at 2 posts/day means each product opens ~12 posts a month. A
# fallback hook that is deterministic per product therefore ships the SAME
# sentence over and over, which is the fastest way to look automated. The
# engine now reads its own published captions back from the committed Pages
# archive (docs/media) — the exact files followers saw — so it remembers what
# it already said. No new state file to commit from CI, no network call, and a
# product added tomorrow builds this memory from its own first post onward.
ARCHIVE_DIR = config.ROOT / "docs" / "media"
_ARCHIVE_READ_LIMIT = 40
_RECENT_HOOK_CACHE: dict[str, list[str]] = {}


def _first_line(path) -> str:
    try:
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
            if line.strip():
                return line.strip()
    except OSError:
        return ""
    return ""


def recent_hooks(product: dict, limit: int = 12) -> list[str]:
    """Opening lines of this product's most recent published captions.

    Newest first. Read-only and best-effort: a missing archive simply means
    "no memory yet". Works for any product id, including one added tomorrow.
    """
    pid = planner.slugify(str(product.get("id") or product.get("name") or ""))
    if not pid:
        return []
    cache_key = f"{pid}|{limit}"
    if cache_key in _RECENT_HOOK_CACHE:
        return list(_RECENT_HOOK_CACHE[cache_key])

    sources: list[tuple[str, object]] = []
    try:
        sources += [
            (d.name, d / "caption.txt")
            for d in sorted((ARCHIVE_DIR / "carousels").glob(f"*_{pid}"))
        ][-_ARCHIVE_READ_LIMIT:]
    except OSError:
        pass
    try:
        sources += [
            (f.name, f)
            for f in sorted((ARCHIVE_DIR / "reels").glob(f"*_{pid}_caption.txt"))
        ][-_ARCHIVE_READ_LIMIT:]
    except OSError:
        pass

    found: list[str] = []
    # Names start with the ISO date, so sorting is chronological.
    for _, path in sorted(sources, key=lambda item: item[0]):
        line = _first_line(path)
        if line and line not in found:
            found.append(line)
    found = found[::-1][:limit]
    _RECENT_HOOK_CACHE[cache_key] = found
    return list(found)


def _hook_key(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).casefold()


# Truthful framings of one catalog detail. Every shape states only what the
# product row states, names the product, and stays inside the 10-word hook
# budget. Volume comes from which detail is used and from rng, not from
# inventing new claims. Second value = words the shape adds besides name/detail.
_HOOK_SHAPES: tuple[tuple[str, int], ...] = (
    ("{detail} — {name}.", 1),
    ("{name}: {detail}.", 0),
    ("{detail}. That's {name}.", 2),
)


def pick_hook(theme: str, product: dict, rng: random.Random) -> str:
    """Specific, truthful fallback hook built only from the active row.

    Deterministic for a given rng seed (so a run is reproducible) but varied
    across dates and concepts, and it skips openings this product already used
    in recent published posts.
    """
    name = str(product.get("name") or "This tool").strip()
    name_words = len(name.split())
    details = [
        *planner.parse_benefits(product),
        str(product.get("specs") or "").strip(),
        str(product.get("trial") or "").strip(),
    ]
    # Keep each detail's full wording (numbers/units stay together); a detail
    # that cannot fit the hook budget is dropped rather than truncated.
    details = [detail.strip().rstrip(".!?") for detail in details if detail.strip()]

    def build(source: list[str]) -> list[str]:
        out: list[str] = []
        for detail in source:
            for shape, fixed_words in _HOOK_SHAPES:
                if len(detail.split()) > 10 - name_words - fixed_words:
                    continue
                text = shape.format(detail=detail, name=name)
                if len(text.split()) > 10 or not punchy(text):
                    continue
                if not hook_coherent(text, product, from_ai=False):
                    continue
                out.append(text)
        return out

    # A detail that carries a number or a plan term is the most concrete thing
    # the row can say, so those lead; otherwise every listed detail competes.
    pool = build([d for d in details if re.search(r"\d", d)]) or build(details)
    if not pool:
        return f"{name}: check the listed details."

    recent = {_hook_key(hook) for hook in recent_hooks(product)}
    fresh = [hook for hook in pool if _hook_key(hook) not in recent]
    return rng.choice(fresh or pool)


def hook_from_concept(concept: dict, product: dict, rng: random.Random) -> str:
    """Generate the same truthful product-specific hook for every concept."""
    return pick_hook(str(concept.get("label") or ""), product, rng)


def build_slide_texts(product: dict, theme: str, rng: random.Random, hook: str = "") -> list[str]:
    """Short, deduplicated product details followed by one honest CTA."""
    slides = [hook or pick_hook(theme, product, rng)]
    seen = {slides[0].strip().casefold()}
    hook_text = slides[0].casefold()
    for detail in [*planner.parse_benefits(product), str(product.get("specs") or "").strip()]:
        detail = detail.strip()
        normalized = detail.casefold()
        if detail and normalized not in seen and normalized not in hook_text:
            slides.append(detail)
            seen.add(normalized)
    slides.append("Check the current terms via the link in bio")
    return slides


def build_caption(
    product: dict, theme: str, for_date: date, rng: random.Random,
    include_hashtags: bool = True, hook: str = "",
) -> str:
    """Truthful, compact fallback caption built only from the product row.

    Reads like a person wrote it: the listed detail, the listed terms, one
    next step, disclosure. No engagement bait and no internal labels.
    """
    name = str(product.get("name") or "This tool").strip()
    benefits = planner.parse_benefits(product)
    trial = str(product.get("trial") or "").strip()
    specs = str(product.get("specs") or "").strip()

    opening = hook or pick_hook(theme, product, rng)
    blocks: list[str] = [opening]
    seen = {opening.strip().casefold()}
    for benefit in benefits[:3]:
        key = benefit.strip().casefold()
        if key and key not in seen and key not in opening.casefold():
            blocks.append(benefit.strip())
            seen.add(key)
    if specs and specs.strip().casefold() not in seen and specs.strip().casefold() not in opening.casefold():
        blocks.append(specs.strip())
        seen.add(specs.strip().casefold())
    if trial and trial.strip().casefold() not in seen and trial.strip().casefold() not in opening.casefold():
        blocks.append(f"{trial.strip().rstrip('.')}.")
    blocks.append(f"Check {name}'s current terms through the link in bio.")
    blocks.append(DISCLOSURE)
    if include_hashtags:
        blocks.append(hashtag_block(product, rng, for_date=for_date))
    return "\n\n".join(blocks)[:2200]


def build_first_comment(product: dict, rng: random.Random,
                         for_date: date | None = None) -> str:
    """Hashtag block goes in the auto-posted first comment (cleaner caption,
    same reach). Posted by the IG publisher right after publishing."""
    return hashtag_block(product, rng, for_date=for_date)[:2200]


# Instagram hard-caps posts/reels at 5 hashtags (2026 policy change; was 30).
# Official creator guidance: 3-5 well-chosen, genuinely descriptive tags.
IG_HASHTAG_LIMIT = 5

# Niche anchors that may appear as the ONE fixed tag per post. Rotation
# rule (Meta hardening 2026-10-02): at most one preferred anchor per post,
# rest sampled fresh — the old "fill all 5 from this list" rule gave every
# post a near-identical hashtag block, a classic automation signature.
_PREFERRED_TAGS = [
    "saas", "saastools", "aitools", "productivity",
    "techstack", "solopreneur", "nocode", "buildinpublic",
]


def hashtag_block(product: dict, rng: random.Random,
                   for_date: date | None = None) -> str:
    tags = load_hashtags()
    pool = list(dict.fromkeys(t if t.startswith("#") else f"#{t}" for t in tags))
    name_words = [w for w in planner.slugify(product["name"]).split("-") if len(w) > 3]
    out = ["#" + w for w in name_words[:2]]
    preferred = [f"#{t}" for t in _PREFERRED_TAGS if f"#{t}" in pool and f"#{t}" not in out]
    if preferred and len(out) < IG_HASHTAG_LIMIT:
        out.append(rng.choice(preferred))
    rest = [t for t in pool if t not in out]
    if rest and len(out) < IG_HASHTAG_LIMIT:
        out += rng.sample(rest, min(IG_HASHTAG_LIMIT - len(out), len(rest)))
    out = out[:IG_HASHTAG_LIMIT]

    # Featured-day swap (2026-10-25): put the fyp-family tag in and drop the
    # block's least important member — the last position, which is always a
    # random pool tag, never the product tag or the chosen anchor. Total stays
    # at the 5-tag cap; rest days are unchanged.
    feat = featured_tag(for_date)
    if feat:
        tag = feat if feat.startswith("#") else f"#{feat}"
        if tag not in out:
            if len(out) >= IG_HASHTAG_LIMIT:
                out = out[:-1]
            out.append(tag)
    return " ".join(out[:IG_HASHTAG_LIMIT])
