"""Optional AI copy upgrade: Google Gemini free tier (no subscription).

The interface intentionally stays optional: model errors or rejected copy
fall through to the product-row template engine without blocking publishing.
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import requests

from core import config, copywriter
from core.boot import setup_console

setup_console()

QUALITY_BAR_PATH = Path(__file__).resolve().parent.parent / "skills" / "marketing" / "QUALITY_BAR.md"


def _quality_bar() -> str:
    try:
        text = QUALITY_BAR_PATH.read_text(encoding="utf-8")
    except OSError:
        return ""
    return re.sub(r"<!--.*?-->\s*", "", text, flags=re.DOTALL).strip()


API = "https://generativelanguage.googleapis.com/v1beta/models"
# Fallback order is by writing quality, not by what happens to answer first.
# 2026-10-28 live probe: the newest model often answers HTTP 503 under free-tier
# load, and the OLD order put the lite model second — so any 503 silently
# downgraded every caption for the whole run. Full models now sit above lite,
# and the retired 2.5 name (HTTP 404) is gone. Failover behaviour is unchanged:
# first model that answers wins and is reused for the rest of the run.
_MODEL_CANDIDATES = [
    "gemini-flash-latest",
    "gemini-3.5-flash",
    "gemini-flash-lite-latest",
    "gemini-3.8-flash",
]
_MODEL_LOCKED = ""


def _attempt(model: str, prompt: str, max_tokens: int, key: str) -> tuple[str | None, str]:
    try:
        r = requests.post(
            f"{API}/{model}:generateContent?key={key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.78,
                    "maxOutputTokens": max_tokens,
                    "responseMimeType": "application/json",
                },
            },
            timeout=90,
        )
        if r.status_code != 200:
            return None, f"{model}: HTTP {r.status_code}"
        cand = r.json()["candidates"][0]
        text = "".join(
            str(part.get("text", ""))
            for part in (cand.get("content") or {}).get("parts", [])
        ).strip()
        return (text or None), ("" if text else f"{model}: empty text (finishReason={cand.get('finishReason')})")
    except Exception as exc:
        return None, f"{model}: {exc!r}"


def _generate(prompt: str, max_tokens: int = 1400, cycles: int = 2) -> str | None:
    """Try the known-good Gemini model first, retaining model failover."""
    global _MODEL_LOCKED
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    order = ([_MODEL_LOCKED] if _MODEL_LOCKED else []) + [
        name for name in _MODEL_CANDIDATES if name != _MODEL_LOCKED
    ]
    for cycle in range(cycles):
        for name in order:
            text, err = _attempt(name, prompt, max_tokens, key)
            if text:
                _MODEL_LOCKED = name
                return text
            if "HTTP 503" in err or "HTTP 429" in err:
                time.sleep(2 + cycle * 3)
    return None


def resolve_model() -> str:
    """First model in the candidate list that answers; cached per run."""
    global _MODEL_LOCKED
    if _MODEL_LOCKED:
        return _MODEL_LOCKED
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return ""
    for name in _MODEL_CANDIDATES:
        try:
            r = requests.post(
                f"{API}/{name}:generateContent?key={key}",
                json={
                    "contents": [{"parts": [{"text": "Reply OK"}]}],
                    "generationConfig": {"maxOutputTokens": 256},
                },
                timeout=60,
            )
            if r.status_code == 200:
                _MODEL_LOCKED = name
                return name
        except Exception:
            continue
    return ""


def available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


SYSTEM_BRIEF = """Write a polished, human-sounding social post for Stack & Save, an affiliate page about SaaS tools.
Use plain US English and varied natural sentence rhythm. Be vivid through concrete reader situations and useful product details, not inflated adjectives.
Use only the product row as factual evidence. A benefit/spec/plan term may be restated accurately; do not invent outcomes, prices, limits, time savings, popularity, urgency, testimonials, or first-person experience. A search phrase or buyer objection is vocabulary/context only, never proof. Do not state unverified research claims. Do not mention competitors, make keyword lists, or use fake questions, engagement bait, contrast reveals, negation lists, trailing add-ons, emojis as bullets, or stale AI clichés.
Write one argument: recognizable reader situation, the relevant product detail, why that detail matters to this reader, then one clear link-in-bio CTA. Make the opening immediately understandable and make the rest repay it. Do not imply we tested or personally use the product. Keep the caption concise and useful; no arbitrary word-count target. On-screen lines must each be one clear idea, short enough to read at a glance.
Return JSON only with keys hook, slides (3-5 concise strings), framework (one of value_stack, problem_proof, hack_list, rant_callout, demo), caption. The caption begins with the exact hook. Do not include hashtags or the affiliate disclosure; code handles disclosure/hashtags."""


_AI_TELLS = (
    r"\b(?:game[- ]changing|revolutionary|next[- ]level|unlock the power|"
    r"in today's fast[- ]paced world|here's the thing|say goodbye to|"
    r"secret (?:to|that)|nobody talks about|everyone is switching|"
    r"most requested|you keep asking|trending|cutting[- ]edge|look no further|"
    r"level up|skyrocket|seamless|effortless|state[- ]of[- ]the[- ]art)\b",
)
_FIRST_PERSON_CLAIM = re.compile(
    r"\b(?:i|we)\s+(?:used|use|tried|tested|earned|made|saved|switched|"
    r"built|grew|replaced|personally)\b", re.IGNORECASE,
)
# The quality bar allows exactly one action: check the current offer at the
# link in bio. Anything that asks for another engagement (or for engagement
# instead of a click) is bait and does not ship.
_CTA_PATTERN = re.compile(r"\blink in (?:the |our )?bio\b|\bbio link\b", re.IGNORECASE)
# An on-screen line that asks for the click is a call to action, whatever
# wording it uses ("check the offer in bio", "check the live offer for trial
# terms"). The renderer already ships its own CTA slide/outro.
_SLIDE_CTA = re.compile(
    r"\bbio\b"
    r"|\b(?:check|see|visit|grab|tap|click)\b[^.]{0,40}\b(?:offer|trial|terms|link|discount)\b",
    re.IGNORECASE,
)
_BAIT_PATTERNS = (
    r"\btag (?:a|your) friends?\b",
    r"\bcomment below\b",
    r"\bdouble[- ]tap\b",
    r"\bdm (?:us|me)\b",
    r"\bthoughts\?",
    r"\bagree\?",
    r"\bwho else\b",
    r"\bsave (?:this|it)\b",
    r"\bshare this\b",
    r"\bdrop a\b",
    r"\blike and (?:share|comment|follow)\b",
    r"\bfollow (?:us|me) for\b",
)
_DISCLOSURE_HINT = re.compile(r"affiliate link|#ad\b|\bcommission\b", re.IGNORECASE)


def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip()).casefold()


def _strip_trailing_disclosure(text: str) -> str:
    """Remove any model-written disclosure so the canonical one is the only one.

    The prompt asks the model to leave disclosure out, but a near-miss wording
    used to end up alongside ours — two disclosures in one caption. Drop
    trailing lines that read like one, then append the canonical sentence.
    """
    lines = text.splitlines()
    while lines:
        tail = lines[-1].strip()
        if not tail:
            lines.pop()
            continue
        if len(tail.split()) <= 25 and _DISCLOSURE_HINT.search(tail):
            lines.pop()
            continue
        break
    return "\n".join(lines).strip()


def _scrub_competitor(text: str, product: dict) -> str:
    """Neutralize direct competitor mentions before validation."""
    alt = str(product.get("alt") or "").strip()
    if not alt or alt.casefold() in {"the old way", "the old platform", str(product.get("name", "")).casefold()}:
        return text
    return re.sub(rf"\b{re.escape(alt)}(?:'s)?\b", "another platform", text, flags=re.IGNORECASE)


def _claim_evidence(product: dict) -> set[str]:
    """Evidence strings that can support a numeric claim about this product."""
    claims = [
        str(product.get("name") or ""),
        str(product.get("price") or ""),
        str(product.get("trial") or ""),
        str(product.get("specs") or ""),
        *copywriter.planner.parse_benefits(product),
    ]
    return {value.strip() for value in claims if value.strip()}


_NUMBER_TOKEN = re.compile(r"\d+(?:[,.]\d+)*")


def _numbers(text: str) -> set[str]:
    """Numeric values in a line, punctuation-insensitive.

    "2,500" and "2500" are the same value, so a catalog that says 2500 must not
    reject copy that writes 2,500 — while an invented 10x/10,000 still fails.
    """
    out: set[str] = set()
    for raw in _NUMBER_TOKEN.findall(str(text or "")):
        digits = re.sub(r"\D", "", raw)
        if digits:
            out.add(digits.lstrip("0") or "0")
    return out


def _unsupported_numbers(text: str, product: dict) -> bool:
    """True when the copy states a number the product row does not support."""
    supported: set[str] = set()
    for evidence in _claim_evidence(product):
        supported |= _numbers(evidence)
    return bool(_numbers(text) - supported)


def _product_relevant(text: str, product: dict) -> bool:
    """The post must be visibly about the featured row, not any SaaS tool."""
    haystack = str(text or "").casefold()
    name = str(product.get("name") or "").strip()
    if name and name.casefold() in haystack:
        return True
    # A distinctive listed detail also identifies the product when the name is
    # long or the copy refers to it by its capability.
    for detail in [
        *copywriter.planner.parse_benefits(product),
        str(product.get("specs") or "").strip(),
    ]:
        if len(detail.split()) >= 3 and detail.casefold() in haystack:
            return True
    return False


def validate_copy(copy: dict, product: dict) -> tuple[bool, str]:
    """Deterministic quality/evidence gate; (accepted, rejection reason)."""
    if not isinstance(copy, dict):
        return False, "copy must be an object"
    hook = str(copy.get("hook") or "").strip()
    slides = copy.get("slides")
    caption = str(copy.get("caption") or "").strip()
    framework = str(copy.get("framework") or "").strip().lower()
    if not hook or not isinstance(slides, list) or not caption:
        return False, "missing hook, slides, or caption"
    if not 1 <= len(hook.split()) <= 10 or not copywriter.punchy(hook):
        return False, "hook is not short and clean"
    if not copywriter.hook_coherent(hook, product, from_ai=True):
        return False, "hook names a competitor"
    clean_slides = [str(line).strip() for line in slides if str(line).strip()]
    if not 2 <= len(clean_slides) <= 5:
        return False, "expected two to five interior lines"
    if any(len(line.split()) > 12 or _normalize(line) == _normalize(hook) for line in clean_slides):
        return False, "slide is long or repeats the hook"
    if len({_normalize(line) for line in clean_slides}) != len(clean_slides):
        return False, "duplicate slide lines"
    if framework not in {"value_stack", "problem_proof", "hack_list", "rant_callout", "demo"}:
        return False, "invalid carousel framework"
    if not caption.startswith(hook):
        return False, "caption must begin with the selected hook"
    if len(caption) > 2200:
        return False, "caption exceeds Instagram's limit"
    if copywriter.DISCLOSURE not in caption:
        return False, "affiliate disclosure missing"
    # Usefulness floor, not a word-count target: a caption that is nothing but
    # the opening plus the disclosure gives the reader no reason to care.
    body = caption[len(hook):] if caption.startswith(hook) else caption
    if len(body.replace(copywriter.DISCLOSURE, "").split()) < 15:
        return False, "caption needs a body beyond the opening line"
    combined = "\n".join([hook, *clean_slides, caption])
    cta_hits = len(_CTA_PATTERN.findall(combined))
    if cta_hits == 0:
        return False, "link-in-bio CTA missing"
    if cta_hits > 2:
        return False, "more than one call to action"
    if any(re.search(pattern, combined, re.IGNORECASE) for pattern in _BAIT_PATTERNS):
        return False, "engagement bait instead of a next step"
    if not _product_relevant(combined, product):
        return False, "copy never names the featured product"
    if _FIRST_PERSON_CLAIM.search(combined):
        return False, "unsubstantiated first-person experience"
    if any(re.search(pattern, combined, re.IGNORECASE) for pattern in _AI_TELLS):
        return False, "stock AI/engagement-bait phrasing"
    if _unsupported_numbers(combined, product):
        return False, "numeric claim is not supported by the product row"
    if _normalize(hook) in {_normalize(used) for used in copywriter.recent_hooks(product)}:
        return False, "opening repeats a recently published post"
    alt = str(product.get("alt") or "").strip()
    if alt and alt.casefold() in caption.casefold():
        return False, "competitor reference remains"
    return True, ""


def pick_retention_hook(options: list | None, model_pick: str = "",
                        product: dict | None = None) -> str:
    """Choose the most concrete clean hook using deterministic, code-owned criteria.

    Model self-scores are intentionally ignored. When a product row is given,
    candidates carrying numbers the row cannot back are dropped before scoring
    (a hook that would be rejected later is not a useful winner), and openings
    this product already used recently lose to fresh ones.
    """
    recent = {_normalize(hook) for hook in copywriter.recent_hooks(product)} if product else set()
    clean: list[str] = []
    for option in options or []:
        text = str(option.get("text", "") if isinstance(option, dict) else option).strip()
        if not text or len(text.split()) > 10 or not copywriter.punchy(text):
            continue
        if _FIRST_PERSON_CLAIM.search(text) or any(re.search(p, text, re.IGNORECASE) for p in _AI_TELLS):
            continue
        if product and _unsupported_numbers(text, product):
            continue
        if text.casefold() not in {_normalize(candidate) for candidate in clean}:
            clean.append(text)
    # A used opening is acceptable only when nothing fresh survives.
    candidates = [text for text in clean if _normalize(text) not in recent] or clean
    if not candidates:
        fallback = str(model_pick or "").strip()
        return fallback if fallback and len(fallback.split()) <= 10 and copywriter.punchy(fallback) else ""

    def score(text: str) -> tuple[int, int, int, str]:
        words = len(text.split())
        has_number = bool(re.search(r"\d", text))
        has_named_subject = bool(re.search(r"\b(?:your|you|when|if|the|a|an)\b", text, re.IGNORECASE))
        return (int(has_number), int(has_named_subject), -words, _normalize(text))

    return max(candidates, key=score)


def _fit_caption(caption: str) -> str:
    """Keep copy readable and within the caption limit without forcing length."""
    text = str(caption or "").replace("\r\n", "\n").strip()
    text = re.sub(r"\s*\((?:source|src):\s*[^)]*\)", "", text, flags=re.IGNORECASE)
    text = re.sub(r"(?i)\blink below\b", "link in bio", text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = _strip_trailing_disclosure(text)
    if not text:
        return ""
    # Drop whole trailing lines rather than cut a sentence or disclosure.
    while len(text) + 2 + len(copywriter.DISCLOSURE) > 2200:
        lines = text.splitlines()
        if len(lines) <= 1:
            return ""
        lines.pop()
        text = "\n".join(lines).rstrip()
    return text + "\n\n" + copywriter.DISCLOSURE


_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


def _first_sentence(text: str) -> str:
    """The opening sentence a caption actually leads with."""
    body = str(text or "").strip()
    if not body:
        return ""
    first_line = body.splitlines()[0].strip()
    return _SENTENCE_END.split(first_line, maxsplit=1)[0].strip()[:180]


def _align_caption(caption: str, hook: str) -> str:
    """Make caption line 1 the shipped hook when a rewrite is actually safe.

    Only a caption that already broke into lines can be realigned. A single
    paragraph is never rewritten here: the opening sentence is chosen as the
    hook in the first place (see parse()), so a mismatch means the draft is
    incoherent and belongs to the rejection path, not to a silent text swap.
    """
    if not hook or caption.startswith(hook):
        return caption
    lines = caption.splitlines()
    if len(lines) < 2:
        return caption
    for index, line in enumerate(lines):
        if line.strip():
            lines[index] = hook
            return "\n".join(lines)
    return caption


# Form guidance per surface. A Reel is watched without sound at speed; a
# carousel is swiped one slide at a time. Same standards, different fit.
_FORM_GUIDANCE = {
    "reel": (
        "This is a Reel: the first frame must be understandable with sound off "
        "and earn the next second. Use 3 on-screen lines, one idea each, all "
        "readable in a glance."
    ),
    "carousel": (
        "This is a carousel: the cover makes a promise a reader can check, and "
        "each interior line has to earn the next swipe. Use 4-5 on-screen "
        "lines, each one understandable on its own."
    ),
}


def write_copy(product: dict, theme: str, fallback_hooks: list[str],
               fallback_slides: list[str], fallback_caption: str,
               brief: dict | None = None, angle: str = "",
               format_name: str = "") -> dict | None:
    """Return validated {'hook','slides','framework','caption'} or None.

    Product-row values are the only source of factual claims. Brief keywords
    and objections guide vocabulary but are explicitly untrusted as proof.
    At most one focused rewrite is requested after an invalid complete draft.
    """
    if not available():
        return None
    trial = str(product.get("trial") or "").strip()
    benefits = copywriter.planner.parse_benefits(product)
    brief = brief or {}

    def bullet(values: list[str], max_count: int = 4) -> str:
        return "\n".join(f"- {value}" for value in values[:max_count]) or "- none"

    # Opening lines this product already used. The model is told to avoid them
    # (and the gate rejects them anyway), so the feed keeps reading as a page
    # written day by day instead of one sentence recycled twelve times a month.
    recent_openings = copywriter.recent_hooks(product, limit=8)
    avoid_block = (
        "\nOpenings already used on this page (do not reuse or lightly reword):\n"
        + bullet(recent_openings, 8)
    ) if recent_openings else ""

    context = (
        f"Product: {product.get('name', '')}\n"
        f"Catalog benefits: {bullet(benefits)}\n"
        f"Catalog specs: {product.get('specs', '')}\n"
        f"Catalog plan/price: {product.get('currency', '')} {product.get('price', '')}; {trial}\n"
        f"Editorial angle: {angle or theme}\n"
        f"Format: {_FORM_GUIDANCE.get(format_name, _FORM_GUIDANCE['carousel'])}\n"
        f"Search vocabulary (not evidence): {bullet(brief.get('keywords', []), 5)}\n"
        f"Buyer questions (not evidence): {bullet(brief.get('objections', []), 3)}\n"
        f"{avoid_block}"
    )
    rules = (
        "Write for one real reader and one specific situation. Use the catalog's "
        "exact facts only. Do not invent a metric, outcome, feature, time saved, "
        "price or trial term. Do not use a first-person customer story or imply "
        "the page tested the tool. Do not use competitor names. Search terms and "
        "questions are not proof. No hype, fake urgency/social proof, engagement "
        "bait, generic opener, or AI stock phrases.\n"
        "Write a useful, short opening that names the reader's situation and "
        "makes a promise the remaining copy pays off. The product name must "
        "appear at least once across the hook, the on-screen lines or the "
        "caption. Give one useful product detail, explain why it matters without "
        "extrapolating, and finish with exactly one link-in-bio action. Vary the "
        "natural sentence rhythm; do not pad.\n"
        "Offer three genuinely different openings: one reader situation, one "
        "catalog detail stated plainly, one decision the reader is facing. Keep "
        "each under 10 words, make a statement (never a question), and use only "
        "numbers that appear in the catalog above.\n"
        "Return JSON only: hooks (3 distinct candidate openings), hook (your "
        "preferred one, copied exactly from hooks), slides (2-5 short unique "
        "on-screen lines, max 12 words each, each a different idea), framework "
        "(value_stack, problem_proof, hack_list, rant_callout, or demo), caption "
        "(natural concise prose that begins with the exact hook). Do not return "
        "self-scores, hashtags or disclosure."
    )
    quality = _quality_bar()
    base_prompt = f"{quality}\n\n---\n\n{SYSTEM_BRIEF}\n\n{context}\n{rules}" if quality else f"{SYSTEM_BRIEF}\n\n{context}\n{rules}"

    def parse(raw: str) -> dict | None:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        raw_hooks = data.get("hooks") or []
        if isinstance(raw_hooks, str):
            raw_hooks = [raw_hooks]
        alternates = [
            str(value) for value in (raw_hooks if isinstance(raw_hooks, list) else [])
        ]
        preferred = str(data.get("hook", "")).strip()
        caption = _fit_caption(str(data.get("caption", "")))
        # Coherence first: the shipped hook is the sentence the caption actually
        # opens with, so the body always pays off the promise. A rejected opener
        # falls back to the next clean candidate, and only then (multi-line
        # captions) to a line-1 rewrite; otherwise the draft fails validation.
        opening = _first_sentence(caption)
        hook = pick_retention_hook([opening], product=product) or pick_retention_hook(
            [preferred, *alternates], product=product
        )
        caption = _align_caption(caption, hook)
        # A repeated on-screen line is a formatting slip, not a reason to lose
        # an otherwise good draft: dedupe and drop the hook when it echoes.
        slides: list[str] = []
        seen = {_normalize(hook)} if hook else set()
        for value in data.get("slides", []) or []:
            line = str(value).strip()
            key = _normalize(line)
            if not line or key in seen:
                continue
            # The renderer already owns the CTA slide/outro; an on-screen line
            # asking for the click is wasted space and doubles the ask.
            if _SLIDE_CTA.search(line):
                continue
            seen.add(key)
            slides.append(line)
        result = {
            "hook": hook,
            "slides": slides,
            "framework": str(data.get("framework", "")).strip().lower(),
            "caption": caption,
        }
        result["hook"] = _scrub_competitor(result["hook"], product)
        result["slides"] = [_scrub_competitor(line, product) for line in result["slides"]]
        result["caption"] = _scrub_competitor(result["caption"], product)
        return result

    prompt = base_prompt
    for attempt in range(2):
        raw = _generate(prompt, max_tokens=1400)
        if not raw:
            return None
        try:
            result = parse(raw)
        except (ValueError, TypeError, KeyError):
            result = None
        if result:
            valid, reason = validate_copy(result, product)
            if valid:
                return result
        else:
            reason = "Return valid JSON with all required fields."
        if attempt == 0:
            prompt = (
                base_prompt + "\n\nCORRECTION: the last draft failed this check: "
                + reason + ". Rewrite once, using only the supplied product-row facts."
            )
    return None
