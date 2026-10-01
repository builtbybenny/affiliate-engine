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
]

DISCLOSURE = "Affiliate link — we may earn a small commission at no extra cost to you. #ad"

# Fallback hashtag pool if data/hashtags.txt is missing (SaaS/tech).
DEFAULT_HASHTAGS = [
    "saas", "saastools", "aitools", "techstack", "productivitytools",
    "solopreneur", "smallbusinesstools", "startuplife", "buildinpublic",
    "nocode", "automation", "marketingtools", "freelancetools",
    "notiontips", "canvatips", "aisaas", "foundertips", "toolstack",
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

    lines: list[str] = []
    lines.append(hook or pick_hook(theme, product, rng))
    lines.append("")
    if benefits:
        lines.append("Why it earns its slot in my stack:")
        for b in benefits:
            lines.append(f"✅ {b}")
        lines.append("")
    if specs := (product.get("specs") or "").strip():
        lines.append(f"⚙️ {specs}")
        lines.append("")
    if trial:
        lines.append(f"🎁 Free trial: {trial}")
        lines.append("")
    if price:
        lines.append(f"💰 {currency} {price}".replace("  ", " "))
        lines.append("")
    lines.append(rng.choice(CTA_LINES))
    lines.append("")
    lines.append(DISCLOSURE)
    if include_hashtags:
        lines.append("")
        lines.append(hashtag_block(product, rng))
    caption = "\n".join(lines)
    return caption[:2200]  # IG hard limit


def build_first_comment(product: dict, rng: random.Random) -> str:
    """Hashtag block goes in the auto-posted first comment (cleaner caption,
    same reach). Posted by the IG publisher right after publishing."""
    return hashtag_block(product, rng)[:2200]


# Instagram hard-caps posts/reels at 5 hashtags (2026 policy change; was 30).
# Official creator guidance: 3-5 well-chosen, genuinely descriptive tags.
IG_HASHTAG_LIMIT = 5

# Niche anchors we prefer whenever they exist in the pool — consistent brand
# positioning beats scattershot tagging now that we only get 5 slots.
_PREFERRED_TAGS = [
    "saas", "saastools", "aitools", "productivity",
    "techstack", "solopreneur", "nocode", "buildinpublic",
]


def hashtag_block(product: dict, rng: random.Random) -> str:
    tags = load_hashtags()
    pool = [t if t.startswith("#") else f"#{t}" for t in tags]
    name_words = [w for w in planner.slugify(product["name"]).split("-") if len(w) > 3]
    out = ["#" + w for w in name_words[:2]]
    for pref in _PREFERRED_TAGS:
        if len(out) >= IG_HASHTAG_LIMIT:
            break
        tag = "#" + pref
        if tag in pool and tag not in out:
            out.append(tag)
    if len(out) < IG_HASHTAG_LIMIT:
        rest = [t for t in pool if t not in out]
        out += rng.sample(rest, min(IG_HASHTAG_LIMIT - len(out), len(rest)))
    return " ".join(out[:IG_HASHTAG_LIMIT])
