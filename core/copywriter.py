"""Copy engine: hooks, captions, hashtags, slide text.

Pure templates — deterministic, free, and editable by anyone. Improve your
copy by editing data/hashtags.txt or the template lists below.
"""
from __future__ import annotations

import random
from datetime import date

from core import config, planner

# Hook templates per theme. {name} = tool, {benefit} = first benefit,
# {price} = price column, {alt} = competitor from 'alt' column.
HOOKS: dict[str, list[str]] = {
    "saas_stack": [
        "5 tools that run my entire business (and what I pay)",
        "My entire {name} workflow in one stack — steal it",
        "The 5-tool stack that replaced a whole team",
    ],
    "before_after": [
        "This {name} workflow took 6 hours. Now: 20 minutes.",
        "Before {name}: chaos. After {name}: {benefit}.",
        "I fired 3 subscriptions after finding {name}",
    ],
    "comparison": [
        "{name} vs {alt}: the honest breakdown",
        "Stop paying for {alt} until you see this",
        "{name} or {alt}? The 5-slide answer",
    ],
    "tutorial_teaser": [
        "The {name} trick nobody tells you about",
        "Do this in {name} before your next launch",
        "Set up {name} once, {benefit} forever",
    ],
    "free_tools": [
        "{name} is free for this — nobody notices",
        "You're paying for tools that have a free tier",
        "5 things you can do with {name} without paying a rupee",
    ],
    "deal_alert": [
        "{name} pricing just changed — check this",
        "If you use {alt}, look at {name}'s pricing page today",
        "Lifetime deal spotted: {name}",
    ],
    "myth_vs_fact": [
        "Myth: you need {alt}. Fact: {name} does it free.",
        "\"{name} is complicated\" — watch me set it up in 60s",
        "Myth: {benefit} needs a big budget. Fact: {name}.",
    ],
}

CTA_LINES = [
    "🔗 Free trial + full breakdown in bio",
    "🔗 I stack all my links in the bio — grab the free trial",
    "📌 Save this · 🔗 bio link has the free-trial link",
    "🔗 Bio link → start free, thank me later",
    "🔗 Everything I use sits behind one bio link — start free",
    "Save this for your next tool audit 📌 — trial link is in the bio 🔗",
    "🔗 Tap the bio link to try it free — I only list tools I actually use",
    "This one earned a permanent slot in my stack 📌 trial link in bio 🔗",
    "📌 Bookmark this. Free trial is one bio-tap away 🔗",
    "🔗 Bio link → try the free tier yourself, no card needed",
]

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


_BANNED_HOOK_WORDS = (
    "supercharge", "unlock", "game-chang", "seamless", "next level",
    "take it to the next", "elevate", "revolutioni",
)


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


def pick_hook(theme: str, product: dict, rng: random.Random) -> str:
    hooks = HOOKS.get(theme) or HOOKS["saas_stack"]
    tpl = rng.choice(hooks)
    benefit = (planner.parse_benefits(product) or ["save hours every week"])[0].lower().rstrip(".")
    return tpl.format(
        name=product["name"],
        benefit=benefit,
        alt=(product.get("alt") or "the old way").strip(),
        price=(product.get("price") or "").strip(),
    )


def hook_from_concept(concept: dict, product: dict, rng: random.Random) -> str:
    """Format a hook from a concept's own bank (concepts.py)."""
    tpl = rng.choice(concept["hooks"])
    benefit = (planner.parse_benefits(product) or ["save hours every week"])[0].lower().rstrip(".")
    # Price display: bare CSV numbers read wrong in hooks ("worth 97").
    # USD gets a $ sign; zero becomes the word "free".
    price = (product.get("price") or "").strip()
    currency = (product.get("currency") or "USD").strip().upper()
    if price == "0":
        price = "free"
    elif price and currency == "USD":
        price = f"${price}"
    return tpl.format(
        name=product["name"],
        benefit=benefit,
        alt=(product.get("alt") or "the old way").strip(),
        price=price,
        trial=(product.get("trial") or "free to start").strip(),
    )


def build_slide_texts(product: dict, theme: str, rng: random.Random, hook: str = "") -> list[str]:
    """Short on-slide headlines: hook first, then benefits, then CTA."""
    slides = [hook or pick_hook(theme, product, rng)]
    slides += [b for b in planner.parse_benefits(product)]
    specs = (product.get("specs") or "").strip()
    if specs:
        slides.append(specs)
    trial = (product.get("trial") or "").strip()
    slides.append(
        f"Free trial: {trial}"
        if trial
        else "Save this 📌  |  Link in bio 🔗"
    )
    return slides


def build_caption(
    product: dict, theme: str, for_date: date, rng: random.Random,
    include_hashtags: bool = True, hook: str = "",
) -> str:
    name = product["name"]
    benefits = planner.parse_benefits(product)
    price = (product.get("price") or "").strip()
    currency = (product.get("currency") or "").strip()
    trial = (product.get("trial") or "").strip()

    # Meta hardening (2026-10-02): rotate structure, bullet marks and
    # section order so consecutive posts don't share an identical skeleton.
    # Every variant carries the same information — only the shape changes.
    variant = rng.randrange(3)
    mark = ("✅", "🔹", "👉")[variant]
    headers = [
        "Why it earns its slot in my stack:",
        "Why I keep it in the rotation:",
        "",  # variant 2: headerless, punchier
    ]
    benefit_block: list[str] = []
    if benefits:
        header = headers[variant]
        benefit_block = ([header] if header else []) + [f"{mark} {b}" for b in benefits]
    info: list[str] = []
    if specs := (product.get("specs") or "").strip():
        info.append(f"⚙️ {specs}")
    if trial:
        info.append(f"🎁 Free trial: {trial}")
    if price:
        info.append(f"💰 {currency} {price}".replace("  ", " "))

    blocks: list[str] = [hook or pick_hook(theme, product, rng)]
    if variant == 0:
        order = [benefit_block, info]
    elif variant == 1:
        order = [info[::-1], benefit_block]
    else:
        order = [[info[0]] if info else [], benefit_block, info[1:]]
    for part in order:
        if part:
            blocks.append("\n".join(part))
    blocks.append(rng.choice(CTA_LINES))
    blocks.append(DISCLOSURE)
    if include_hashtags:
        blocks.append(hashtag_block(product, rng))
    caption = "\n\n".join(blocks)
    return caption[:2200]  # IG hard limit


def build_first_comment(product: dict, rng: random.Random) -> str:
    """Hashtag block goes in the auto-posted first comment (cleaner caption,
    same reach). Posted by the IG publisher right after publishing."""
    return hashtag_block(product, rng)[:2200]


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


def hashtag_block(product: dict, rng: random.Random) -> str:
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
    return " ".join(out[:IG_HASHTAG_LIMIT])
