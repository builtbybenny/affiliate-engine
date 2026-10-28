"""What already resonates: shape-only signal from public Instagram posts.

Some posts already work for these products. This module reads them through
Instagram's Business Discovery endpoint (public professional accounts only,
the account list lives in data/pattern_sources.csv) and turns them into
GUIDANCE about form: how the strongest openings are built, and which topics
over-index.

It deliberately never carries wording, claims or numbers across. Instagram's
own originality guidance treats a reworded repost as a superficial edit, and
an account that repeats other people's material can lose recommendation reach
— the only distribution a small account has. Shape is not copyrightable and
is the part worth learning from; facts stay in the product row.

Rotation: this runs on one day in ROTATION_DAYS, not on every post, and the
decision comes from the date alone so a local run and a CI run agree without
any shared state to commit. Everything here is best-effort: no account
configured, no token, a rate limit, an API error or an unparseable caption all
degrade to "no signal" and generation carries on.
"""
from __future__ import annotations

import csv
import re
from datetime import date

import requests

from core import config

SOURCES_CSV = config.DATA_DIR / "pattern_sources.csv"

# One post in every ROTATION_DAYS uses the mined signal. The value is applied
# to the date ordinal, so the pattern alternates 3-4 calendar days in practice
# (month/week boundaries) and never depends on stored state.
ROTATION_DAYS = 3

_POST_LIMIT = 12          # recent posts read per account
_TIMEOUT = 20             # seconds; this must never stall a posting run
_API = "https://graph.facebook.com"

_BRIEF_CACHE: dict[str, str] = {}

# Topic buckets: used only to COUNT what the strongest posts are about, never
# to quote them. Order matters — the first bucket that matches wins.
_TOPICS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("pricing and plan changes", re.compile(
        r"\b(?:pricing|price|cost|free|plan|tier|discount|billing|subscription|\$\d)", re.I)),
    ("new features and launches", re.compile(
        r"\b(?:launch|now live|new feature|introduc|update|redesign|dashboard|release|shipping)\b", re.I)),
    ("customer proof and stories", re.compile(
        r"\b(?:customer|case study|congrat|grew|earned|success|story|creator|founder|testimonial)\b", re.I)),
    ("comparisons and switching", re.compile(
        r"\b(?:vs\.?|versus|alternative|compared|switch|instead of|better than)\b", re.I)),
    ("how-to and tips", re.compile(
        r"\b(?:how to|guide|tips|steps|tutorial|learn|checklist)\b", re.I)),
    ("platform news and ads", re.compile(
        r"\b(?:podcast|ads?|algorithm|policy|update from|announce)\b", re.I)),
)

_IMPERATIVE_OPENERS = (
    "stop", "start", "try", "get", "build", "launch", "save", "quit", "ditch",
    "use", "pick", "choose", "skip", "avoid", "check", "turn", "make",
)


def rotation_day(for_date: date | None = None) -> bool:
    """True on the days that use the mined signal (date-driven, stateless)."""
    d = for_date or config.now_local().date()
    return d.toordinal() % ROTATION_DAYS == 0


def accounts_for(product: dict) -> list[str]:
    """Watched Instagram accounts for this product (empty for unknown rows).

    A product missing from the CSV simply has no signal — adding one is a
    one-line change, and new products need no code edit.
    """
    pid = str(product.get("id") or product.get("name") or "").strip().lower()
    if not pid:
        return []
    try:
        with open(SOURCES_CSV, newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except OSError:
        return []
    accounts: list[str] = []
    for row in rows:
        if str(row.get("product_id") or "").strip().lower() != pid:
            continue
        account = str(row.get("account") or "").strip().lstrip("@")
        if account and account not in accounts:
            accounts.append(account)
    return accounts


def _fetch_posts(username: str) -> list[dict]:
    """Public media for one professional account; [] on any failure."""
    token = config.ACCESS_TOKEN
    if not (token and config.IG_USER_ID):
        return []
    fields = (
        f"business_discovery.username({username})"
        f"{{media.limit({_POST_LIMIT}){{caption,like_count,comments_count,timestamp}}}}"
    )
    try:
        response = requests.get(
            f"{_API}/{config.GRAPH_VERSION}/{config.IG_USER_ID}",
            params={"fields": fields, "access_token": token},
            timeout=_TIMEOUT,
        )
        if response.status_code != 200:
            return []
        media = (
            response.json().get("business_discovery", {}).get("media", {}).get("data", [])
        )
    except Exception:
        return []
    posts: list[dict] = []
    for item in media if isinstance(media, list) else []:
        caption = str(item.get("caption") or "").strip()
        if not caption:
            continue  # no text to learn form from
        posts.append({
            "caption": caption,
            "likes": int(item.get("like_count") or 0),
            "comments": int(item.get("comments_count") or 0),
        })
    return posts


def engagement(post: dict) -> int:
    """Comments weigh double: they cost the reader more than a like."""
    return int(post.get("likes") or 0) + 2 * int(post.get("comments") or 0)


def _first_line(caption: str) -> str:
    for line in str(caption or "").splitlines():
        clean = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", "", line).strip()
        if clean:
            return clean
    return ""


def hook_kind(caption: str) -> str:
    """Opening shape of a post, classified from the text alone."""
    line = _first_line(caption)
    if not line:
        return "unknown"
    if line.endswith("?"):
        return "question"
    if re.match(r"^[\$€£₹]?\d", line) or re.search(r"\d+(?:[,.]\d+)?%?", line[:40]):
        return "number-led"
    if re.match(r"^(?:you|your|you're|yourself)\b", line, re.I):
        return "you-led"
    first_word = re.match(r"^[A-Za-z']+", line)
    if first_word and first_word.group(0).lower() in _IMPERATIVE_OPENERS:
        return "imperative"
    return "statement"


def topic_of(caption: str) -> str:
    for name, pattern in _TOPICS:
        if pattern.search(caption):
            return name
    return "other"


def top_posts(posts: list[dict], share: int = 3) -> list[dict]:
    """Strongest third of each account, pooled (so a bigger account cannot
    dominate just by having more likes)."""
    if not posts:
        return []
    ranked = sorted(posts, key=engagement, reverse=True)
    # At least two, so a thin account still contributes a comparable pair
    # instead of a single post the digest cannot judge.
    keep = min(len(ranked), max(2, len(ranked) // share))
    return ranked[:keep]


def digest(posts: list[dict], product_name: str) -> str:
    """Compact guidance about form and topics — never wording or claims.

    Only openings this page is allowed to use are reported. A question hook or
    a 14-word first line performs for someone else, but our own gates reject
    both, so teaching the writer those shapes would just create drafts that
    fail validation.
    """
    strong = top_posts(posts)
    usable = [post for post in strong if hook_kind(post["caption"]) != "question"]
    if len(usable) < 2:
        return ""
    kinds: dict[str, int] = {}
    topics: dict[str, int] = {}
    short_openings = 0
    for post in usable:
        kind = hook_kind(post["caption"])
        if kind != "unknown":
            kinds[kind] = kinds.get(kind, 0) + 1
        topic = topic_of(post["caption"])
        topics[topic] = topics.get(topic, 0) + 1
        if len(re.findall(r"\S+", _first_line(post["caption"]))) <= 10:
            short_openings += 1
    if not kinds:
        return ""

    kind, kind_n = max(kinds.items(), key=lambda kv: (kv[1], kv[0]))
    ranked_topics = sorted(topics.items(), key=lambda kv: (-kv[1], kv[0]))
    topic_text = ", ".join(
        name for name, count in ranked_topics[:2] if name != "other" and count
    )

    parts = [
        f"Public Instagram posts about {product_name} were read to learn form, "
        f"not content ({len(strong)} strongest of {len(posts)}).",
        f"{kind_n} of {len(usable)} open with a {kind} line, and "
        f"{short_openings} of {len(usable)} keep that line under 10 words.",
    ]
    if topic_text:
        parts.append(f"Topics that over-index among them (names only): {topic_text}.")
    parts.append(
        "Use this only to choose the angle and opening shape. Their wording, "
        "claims and numbers are not evidence and must not be reused."
    )
    return " ".join(parts)


def brief_for(product: dict, for_date: date | None = None,
              allow_network: bool = True) -> str:
    """Signal string for this product on this date ("" on rest days)."""
    d = for_date or config.now_local().date()
    if not rotation_day(d):
        return ""
    accounts = accounts_for(product)
    if not accounts or not allow_network:
        return ""
    cache_key = f"{product.get('id') or product.get('name')}|{d.isoformat()}"
    if cache_key in _BRIEF_CACHE:
        return _BRIEF_CACHE[cache_key]
    posts: list[dict] = []
    for account in accounts:
        posts.extend(_fetch_posts(account))
    text = digest(posts, str(product.get("name") or "this tool"))
    _BRIEF_CACHE[cache_key] = text
    return text
