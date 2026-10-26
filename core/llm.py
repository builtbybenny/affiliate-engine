"""Optional AI copy upgrade: Google Gemini free tier (no subscription).

If GEMINI_API_KEY exists in .env, captions, hooks, and slide text get written
by the model using your product data; every failure path silently falls back
to the built-in template engine, so the system never stalls on the AI.

Get a key free: https://aistudio.google.com/app/apikey (generous free tier,
no card). Put GEMINI_API_KEY=... in .env. Remove it to go full-template.
Model names are self-healing: if Google retires one, the next candidate is
tried automatically (see _MODEL_CANDIDATES).
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

# Vendored marketing quality bar (skills/marketing/QUALITY_BAR.md — see
# VENDORED.md). Prepended to the caption/hook prompt: a short, sharp list of
# hard bans + composition rules distilled from coreyhaines31/marketingskills
# (MIT, pinned f719a807). Missing file = skip gracefully: caption generation
# must never die on a vendored text file.
QUALITY_BAR_PATH = Path(__file__).resolve().parent.parent / "skills" / "marketing" / "QUALITY_BAR.md"


def _quality_bar() -> str:
    """Compact rule block for the prompt; '' when missing/unreadable."""
    try:
        text = QUALITY_BAR_PATH.read_text(encoding="utf-8")
    except OSError:
        print("  (marketing quality bar missing — continuing without)")
        return ""
    # strip the HTML provenance comment — prompt tokens only
    return re.sub(r"<!--.*?-->\s*", "", text, flags=re.DOTALL).strip()

API = "https://generativelanguage.googleapis.com/v1beta/models"

# Google retires model names over time, so we keep an ordered candidate list
# and remember the first one that answers. Update by appending newer names.
_MODEL_CANDIDATES = [
    "gemini-flash-latest",     # stable rolling alias
    "gemini-flash-lite-latest", # lighter = less contended, fine for short copy
    "gemini-3.8-flash",        # newest; sometimes 503s under load
    "gemini-3.5-flash",
    "gemini-2.5-flash",        # retired for new users; kept as last resort
]
_MODEL_LOCKED = ""


def _attempt(model: str, prompt: str, max_tokens: int, key: str) -> tuple[str | None, str]:
    """One generation attempt. Returns (text, error_note)."""
    try:
        r = requests.post(
            f"{API}/{model}:generateContent?key={key}",
            json={
                "contents": [{"parts": [{"text": prompt}]}],
                "generationConfig": {
                    "temperature": 0.9,
                    "maxOutputTokens": max_tokens,
                    "responseMimeType": "application/json",
                },
            },
            timeout=90,  # generous: thinking + JSON generation
        )
        if r.status_code != 200:
            return None, f"{model}: HTTP {r.status_code}"
        cand = r.json()["candidates"][0]
        # join ALL parts (thinking models may split content across parts)
        text = "".join(
            str(p.get("text", "")) for p in (cand.get("content") or {}).get("parts", [])
        ).strip()
        return (text or None), ("" if text else f"{model}: empty text (finishReason={cand.get('finishReason')})")
    except Exception as e:
        return None, f"{model}: {e!r}"


def _generate(prompt: str, max_tokens: int = 2400, cycles: int = 2) -> str | None:
    global _MODEL_LOCKED
    # 2400 headroom: thinking models burn output tokens reasoning before
    # writing the JSON, so small budgets silently truncate the answer.
    key = os.getenv("GEMINI_API_KEY", "").strip()
    if not key:
        return None
    # Try the cached-good model first, then every other candidate —
    # demand on individual models is spiky (503s come and go within
    # seconds), so we sweep the list twice with a short backoff.
    order = ([_MODEL_LOCKED] if _MODEL_LOCKED else []) + [
        m for m in _MODEL_CANDIDATES if m != _MODEL_LOCKED
    ]
    for cycle in range(cycles):
        for name in order:
            text, err = _attempt(name, prompt, max_tokens, key)
            if text:
                _MODEL_LOCKED = name
                return text
            if "HTTP 503" in err or "HTTP 429" in err:
                time.sleep(2 + cycle * 3)  # brief backoff on capacity errors
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
                    # Probe with a realistic budget: thinking models spend
                    # output tokens reasoning first, tiny budgets return
                    # empty text and can even be rejected.
                    "generationConfig": {"maxOutputTokens": 512},
                },
                timeout=60,  # thinking models can be slow even on trivia
            )
            if r.status_code == 200:
                _MODEL_LOCKED = name
                return name
        except Exception:
            continue
    return ""


def available() -> bool:
    return bool(os.getenv("GEMINI_API_KEY", "").strip())


SYSTEM_BRIEF = (
    "You write Instagram/Facebook content for 'Stack & Save', a faceless "
    "theme page promoting SaaS tools via affiliate free-trial links. "
    "Voice: sharp, specific, honest; no hype, no income claims, no emojis in "
    "ON-SLIDE text (emojis OK inside captions). US spelling. Short sentences.\n\n"
    "SCROLLER-FIRST RULE (most important): a casual scroller often has the "
    "PROBLEM without knowing the tool category or product names. Never open "
    "with a tool name or a competitor name. Open with the human moment: the "
    "pain, chaos, cost or wasted time the reader recognizes from their own "
    "life. Introduce the tool name only AFTER the reader feels understood, as "
    "the answer to that moment. Plain words a non-tech person gets: no jargon "
    "like CRM, CMS, funnel builder, no-code unless you first explain the "
    "everyday situation they solve.\n\n"
    "PUNCH RULE (2026-10-05 quality pass): every line must hit like a claim, "
    "not a suggestion. Hooks are STATEMENTS with tension — a number, a cost, "
    "a before/after gap, or a specific absurdity ('Your dead site loses you a "
    "customer every 30 seconds'). BANNED: soft rhetorical questions as the "
    "hook ('Tired of X?'), vague hype ('take it to the next level', "
    "'supercharge', 'unlock', 'game-changing', 'seamless'), and any line that "
    "could describe 10 different tools unchanged. If a line works for a "
    "competitor's post as-is, rewrite it until it only fits this tool. Numbers "
    "beat adjectives. Keep hook lines under 10 words.\n\n"
    "SELLING RULE (2026-10-25 content rebuild — this is an ad with a link "
    "behind it, not a lesson): every post moves ONE reader across ONE gap. "
    "Shape: the gap they already feel -> this tool closing it (one checkable "
    "fact) -> what their week looks like after -> ONE ask (free trial, link "
    "in bio). The reader must finish knowing exactly what to do next.\n"
    "BANNED CLAIMS (we have no data for any of them): 'most requested', "
    "'you keep asking', 'back again', 'here it is again', 'X people grabbed "
    "this', 'hundreds/thousands of users', 'everyone is switching', "
    "'trending', and any invented popularity, sales or usage number.\n"
    "BANNED SHAPES: feature tours ('here's what it does: ...'), spec lists, "
    "product-page copy, tutorials, and generic 'benefits of X' roundups — if "
    "the post could be about any tool, it is not written yet.\n"
    "Never promise a result the researched facts do not support, and never "
    "claim we personally achieved something we did not."
)


def pick_retention_hook(options: list | None, model_pick: str = "") -> str:
    """Choose the hook most likely to survive the first 3 seconds.

    Candidates arrive from write_copy() as [{'text':..., 'score':...}] —
    the model's self-score, adjusted by measurable retention signals
    (a number on screen, brevity) and hard-filtered by the punch gate.
    Chosen 2026-10-05: skip rate is upstream of every other metric, so
    hook selection is code, not vibes.
    """
    best, best_score = "", -1
    for opt in options or []:
        if isinstance(opt, dict):
            text, base = str(opt.get("text", "")).strip(), opt.get("score")
        else:
            text, base = str(opt).strip(), None
        if not text or not copywriter.punchy(text) or len(text.split()) > 10:
            continue
        try:
            score = int(base)
        except Exception:
            score = 50
        if any(ch.isdigit() for ch in text):
            score += 15          # numbers are read even at scroll speed
        if len(text.split()) <= 8:
            score += 10          # fits one glance on the first frame
        if text.endswith("."):
            score += 5           # landed statement, not trailing doubt
        if score > best_score:
            best, best_score = text, score
    if best:
        return best
    mp = str(model_pick or "").strip()
    return mp if mp and copywriter.punchy(mp) else ""


def _reflow(text: str) -> str:
    """Repair a caption the model returned as one wall of text.

    Line breaks are the whole readability game on mobile — if the model
    crammed its 5-7 intended lines into a paragraph, split at bullets and
    sentence boundaries so every thought gets its own line.
    """
    if text.count("\n") >= 3:
        return text
    text = text.replace(" • ", "\n• ").replace(". •", ".\n•")
    if text.count("\n") >= 3:
        return text
    # sentence-per-line fallback (IG-native formatting anyway)
    text = re.sub(r"(?<=[.!?]) +(?=[A-Z•])", "\n", text)
    return text


def _fit_caption(caption: str, primary_phrase: str = "") -> str:
    """Keep the caption inside IG's 2,200-char cap with room for the folded
    hashtag block (~90 chars), and guarantee the canonical disclosure line.
    Cuts at a line boundary — never mid-sentence.

    primary_phrase: the SEO keyword the spec told the model to use at most
    twice (line 1 + one body line). Lines 3+ stuffing it get rewritten to
    drop the phrase — the prompt rule alone failed (2026-10-11 gohighlevel
    reel said 'all in one crm for agencies' three times in five lines).
    """
    text = _reflow((caption or "").strip())
    # Research provenance is grounding for the writer, not copy for the
    # viewer — it leaked into live captions (2026-10-06/07 reels) and the
    # caption .txt files are public on Pages. Strip it here, at generation.
    text = re.sub(r"\s*\((?:source|src):\s*[^)]*\)", "", text, flags=re.IGNORECASE)
    text = text.replace("link below", "link in bio")  # reels link lives in bio
    # Keyword discipline (see docstring): keep the phrase in its first TWO
    # lines, strip it from later lines. Case-insensitive whole-phrase match.
    phrase = (primary_phrase or "").strip().lower()
    if phrase and len(phrase) > 8:  # trivially short phrases aren't SEO keys
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        uses = 0
        fixed: list[str] = []
        for line in text.split("\n"):
            if uses >= 2:
                line = pattern.sub("", line)
                line = re.sub(r"\s{2,}", " ", line).strip()
                # tidy punctuation left dangling by the removal
                line = re.sub(r"^[，,;:.\s]+", "", line)
                line = re.sub(r"\s+([.,;!?])", r"\1", line)
            if pattern.search(line):
                uses += 1
            fixed.append(line)
        text = "\n".join(fixed)
    lines = [l for l in text.split("\n")
             if not l.strip().startswith("Affiliate link")]
    body: list[str] = []
    for line in lines:
        used = sum(len(x) + 1 for x in body)
        if used + len(line) + 2 > 2000:
            break
        body.append(line)
    out = "\n".join(body).strip()
    if not out:
        return ""
    return out + "\n\n" + copywriter.DISCLOSURE


def _scrub_competitor(text: str, product: dict) -> str:
    """Replace the rival's brand name with a neutral phrase (2026-10-26).

    Belt to the prompt's braces: naming the competitor is banned in writing,
    and models still did it in 4 of 8 probe captions because the name is in
    the prompt as positioning context. The body has no gate that can reject a
    line, so the guarantee has to be mechanical: 'Mailchimp charges you for
    dead subscribers' -> 'The old platform charges you for dead subscribers',
    capitalised when it opens a line or a sentence.
    """
    alt = (product.get("alt") or "").strip()
    if not alt or alt.lower() in {"the old way", "", product.get("name", "").lower()}:
        return text

    def _sub(m: re.Match) -> str:
        before = text[max(0, m.start() - 2):m.start()]
        starts = m.start() == 0 or before.endswith(("\n", ". ", "! ", "? ", "• ", "- "))
        # 'Your Mailchimp list' must not become 'Your the old platform list' —
        # drop the article when a determiner already sits in front of it.
        lead = re.search(r"(\w+)\s*$", text[:m.start()])
        bare = bool(lead) and lead.group(1).lower() in {
            "your", "the", "a", "an", "my", "our", "their", "its", "that", "this",
        }
        if bare:
            base = "Old platform" if starts else "old platform"
        else:
            base = "The old platform" if starts else "the old platform"
        return base + ("'s" if m.group(0).lower().endswith("'s") else "")

    return re.sub(rf"\b{re.escape(alt)}(?:'s)?\b", _sub, text, flags=re.IGNORECASE)


def write_copy(product: dict, theme: str, fallback_hooks: list[str],
               fallback_slides: list[str], fallback_caption: str,
               brief: dict | None = None, angle: str = "") -> dict | None:
    """Returns {'hook': str, 'slides': [..], 'caption': str} or None on any failure.

    brief: per-product research brief (core/briefs) — search keywords real
    people use, attributable blog facts, buyer objections, pain-led angles.
    Without it the model writes from product data alone.

    angle: the ONE user-journey gap this post is built around (from the
    concept's ``journey`` field). Added 2026-10-25 — without it every post
    came back as the same benefit list in different words.

    The hook is chosen by pick_retention_hook() from 4 scored candidates;
    the caption is the detailed SEO spec (2026-10-05 content review).
    """
    if not available():
        return None
    trial = (product.get("trial") or "").strip()
    brief = brief or {}
    research_block = ""
    if brief:
        def _lines(key: str) -> str:
            return "\n".join(f"- {v}" for v in brief.get(key, [])[:8]) or "- (none)"
        research_block = (
            "\nRESEARCHED FOR THIS TOOL (from real news + marketing blogs — "
            "ground the caption in these, never invent facts):\n"
            "Search phrases people actually type:\n" + _lines("keywords") + "\n"
            "Facts/stats you may cite (keep the source note):\n" + _lines("facts") + "\n"
            "Buyer objections to answer:\n" + _lines("objections") + "\n"
            "Pain-led angle seeds (rewrite them, don't quote):\n" + _lines("angles") + "\n"
        )
    prompt = (
        f"{SYSTEM_BRIEF}\n\n"
        f"Tool: {product['name']}\n"
        f"Key benefits: {product.get('benefits', '')}\n"
        f"Specs: {product.get('specs', '')}\n"
        f"Free trial: {trial}\n"
        f"Price: {product.get('currency', '')} {product.get('price', '')}\n"
        f"Competitor to position against: {product.get('alt', 'the old way')}\n"
        f"Post theme: {theme}\n"
        f"THE ONE JOURNEY GAP THIS POST CLOSES: "
        f"{angle or 'the pain the tool removes, made specific'}\n"
        f"{research_block}\n"
        "RETENTION RULES (skip rate decides distribution — first 3 seconds are "
        "the whole game):\n"
        "- The hook is a PROMISE the first on-screen scene repays immediately; "
        "it must be readable with sound off in one glance (max 9 words).\n"
        "- Specificity beats drama: numbers, dollars, minutes, before/after gaps. "
        "A hook that fits 10 different tools is dead.\n"
        "- Never open with the product or brand name — the frame already shows it. "
        "Pain first, tool as the answer. Never a soft question.\n"
        "- No intro energy: no 'hey', no context-setting, no 'in this post'.\n"
        "- The hook appears exactly ONCE: as caption line 1 and as scene 1 on "
        "screen. It must not come back as a later caption line, a slide, or an "
        "on-screen reminder — a repeated opening line reads as a loop.\n\n"
        "SALES SPINE (why this post exists):\n"
        "- GAP: one specific, felt moment the reader recognizes from their own "
        "week — cost, time lost, or a result stuck short. Make it concrete in "
        "the first two lines.\n"
        "- FIX: introduce the tool as the answer to THAT gap, with one "
        "checkable fact from the researched list (price, limit, trial terms).\n"
        "- AFTER-STATE: what the reader's week looks like once the gap is "
        "closed — one vivid outcome line, in their words, not the spec sheet's.\n"
        "- ONE ASK: end on a decision (free trial, link in bio). No menu of "
        "options, no 'save this for later' as the closing move, no second CTA.\n"
        "- Do not paste the product's benefit list: every • line is the "
        "viewer's after-state, phrased differently from the last post. A "
        "feature ('3D analytics') is never a benefit ('you see which post "
        "earned the subscriber before your coffee').\n\n"
        "SCROLLER-FIRST STRUCTURE:\n"
        '- "hook_options": 4 candidate hooks — each a statement under 10 words, '
        "each weaving in the primary search phrase (so whichever one gets "
        "chosen, the post still opens on the keyword), each seeded from the "
        "researched angles where they fit, each with "
        '"score": 0-100 for how likely it survives the first 3 seconds '
        "(reward: a number, immediate problem recognition, a concrete cost; "
        "punish: vagueness, tool-name openings, anything a competitor could say).\n"
        '- "hook": your single best pick from hook_options; caption line 1 must '
        "be VERBATIM that same sentence — the on-screen hook and the caption "
        "open with identical words.\n"
        "- CAROUSEL ARCHITECTURE (vendored carousel-frameworks.md — this deck "
        "is a swipe-through, not a blog post chopped into squares): pick ONE "
        f"framework, name it in \"framework\" (one of: value_stack, "
        "problem_proof, hack_list, rant_callout, demo) and obey it end to "
        "end — 'value_stack': slide 1 states an exact count + exact "
        "deliverable, then each interior slide pays down exactly one item; "
        "'problem_proof': a numbered result claimed on slide 1, the real "
        "problem stated, the mechanism, the how-to detail, then the proof; "
        "'hack_list': a tight count of techniques, one technique per slide; "
        "'rant_callout': one bold stance on a common practice argued through; "
        "'demo': a step 1..N walkthrough ending in the outcome. Slide 1 must "
        "ALSO stand alone as a feed thumbnail. Every slide delivers ONE idea "
        "and makes the next swipe irresistible; interior slides may name the "
        "tool; the final slide is the free-trial close.\n"
        "- No filler slides: each slide line is unique within the deck — a "
        "repeated line reads as the same slide twice and kills the swipe.\n\n"
        "SEO CAPTION SPEC (detailed — this caption is meant to rank in IG + "
        "Google search):\n"
        "- 170-240 words. This floor is a HARD requirement: a caption under "
        "170 words is not finished. Before you answer, count — you need the "
        "hook line, the keyword line, 4 bullets (each carrying a real number), "
        "a two-sentence objection answer, an after-state line, one question and "
        "the CTA. Shorter means you skipped one of those; add the detail, do not "
        "pad with new claims.\n"
        "- Line 1: the primary search phrase woven into the hook statement — an "
        "absolute claim, never a question, never tool-name-first. Line 1 is "
        "VERBATIM the hook you chose (same words, no rewrite). The primary "
        "search phrase must appear within the first two lines. The literal "
        f"product name '{product['name']}' MUST appear in the body (one middle "
        "line introduces it as the fix). Never name the competitor.\n"
        "- Never invent trial lengths, discounts, promo codes, or prices — use "
        "only the Free trial / Price values given above.\n"
        "- Never name a competitor anywhere in the caption (not even in line 1): "
        "say 'the old way', 'the usual platform', 'what you pay for now'. The "
        "competitor is the product's alt column, given above — it is context for "
        f"your positioning only. The literal string '{product.get('alt', '')}' "
        "must not appear in your hook, your slides or your caption — not "
        "capitalized, not lowercase, not in a comparison.\n"
        "- The caption MUST use literal line breaks: 5-7 separate lines, one "
        "thought per line, each • bullet on its own line — never one paragraph.\n"
        "- Body: 3-5 short lines. Include the primary keyword phrase exactly "
        "ONCE more in the body (light repetition only — the play-it-3-times "
        "advice from 2026-10-05 produced visible stuffing that reads as spam "
        "to humans and ranking models alike). All other lines use different "
        "researched phrases or plain benefit language. Cite 2 researched "
        "facts with "
        "their short source note. Benefits as • lines with real numbers.\n"
        "- DESIRE STAGE (the missing AIDA beat — added 2026-10-12): benefit "
        "bullets paint the VIEWER'S after-state, not the tool's spec. Show "
        "what their day/week looks like once the workflow exists — outcome "
        "+ concrete detail beats feature recital: NOT a feature like 3D "
        "analytics, but the viewer's moment it enables (which subscriber "
        "earns, before coffee). At least 1 of the 3-5 body lines must be "
        "outcome-toned; the others stay factual.\n"
        "- Any CTA says 'link in bio' (never 'link below').\n"
        "- Keep each cited fact's (source: ...) note exactly as given.\n"
        "- Example of the SHAPE expected (write your own content, same bones):\n"
        "  Stop paying for tools you open twice a month.\n"
        "  [primary search phrase] + the old way's cost, in one sentence.\n"
        "  • Move your list over in one import, zero downtime\n"
        "  • Free tier covers 2,000 subscribers (source: site pricing page)\n"
        "  Which would you migrate first — your list or your automations?\n"
        "  ToolName does this in one click and charges nothing until you scale.\n"
        "  Start free with the link in bio — no card needed.\n"
        "  (that shape runs 170-240 words when the lines carry real detail)\n"
        "- Answer ONE buyer objection from the researched list in plain words.\n"
        "- KEYWORD DISCIPLINE: the primary search phrase may appear at most "
        "TWICE in the whole caption (once in line 1, once in the body). A "
        "third appearance is over-optimization — rewrite the line instead.\n"
        "- Exactly ONE specific engagement question after line 1 (references this "
        "content, e.g. which benefit they'd use first) — comments are a ranking "
        "signal.\n"
        f"- One CTA line about the free trial{' (' + trial + ')' if trial else ''}.\n"
        "- Do NOT write the affiliate disclosure — it is appended automatically.\n\n"
        "Return STRICT JSON with keys: hook_options (4 objects), hook, slides "
        "(3-6 strings, max 12 words each), framework (one of: value_stack, "
        "problem_proof, hack_list, rant_callout, demo), caption. No other "
        "keys. JSON only."
    )
    def _parse(raw: str) -> dict | None:
        data = json.loads(raw)
        options = data.get("hook_options") or []
        hook = pick_retention_hook(options, str(data.get("hook", "")))
        slides = [str(s).strip() for s in data.get("slides", []) if str(s).strip()]
        # One idea per slide (carousel-frameworks.md): reject a deck that
        # repeats a line — the retry below gets a sharper spec than a bad reel.
        if len({s.lower() for s in slides}) < len(slides):
            return None
        framework = str(data.get("framework", "")).strip().lower()
        if framework not in ("value_stack", "problem_proof", "hack_list", "rant_callout", "demo"):
            framework = "value_stack"
        caption = _fit_caption(str(data.get("caption", "")),
                               primary_phrase=(brief.get("keywords") or [""])[0])
        if not (hook and slides and caption):
            return None
        # Deterministic competitor scrub (2026-10-26): the prompt bans naming
        # the rival, yet 4 of 8 probe captions did it the moment the name sat
        # in the prompt — 'Stop paying Mailchimp when free tools exist'. The
        # gate below can only reject a hook, never a body line, so swap the
        # brand for a neutral phrase here and guarantee it never ships.
        hook = _scrub_competitor(hook, product)
        slides = [_scrub_competitor(s, product) for s in slides]
        caption = _scrub_competitor(caption, product)
        return {"hook": hook, "slides": slides[:6], "framework": framework, "caption": caption}

    # Quality bar FIRST (fresh every call — the vendored file can change via
    # marketing_distill without touching this code).
    bar = _quality_bar()
    if bar:
        prompt = f"{bar}\n\n---\n\n{prompt}"

    # Models undershoot length targets; bounded retries (2026-10-05 the
    # user picked max-detail captions — 130 words was consistently short;
    # 2026-10-26 a third attempt was added because 2/16 probe captions still
    # landed under the 160-word floor twice in a row). The nudge carries the
    # ACTUAL word count so the model corrects a specific deficit, not a vibe.
    attempt_prompt = prompt
    last: dict | None = None
    for _ in range(3):
        raw = _generate(attempt_prompt)
        if not raw:
            return last
        try:
            out = _parse(raw)
        except Exception:
            return last
        if out and len(out["caption"].split()) >= 160:
            return out
        if out:
            last = out  # usable but short — retry once for more detail
            wc = len(out["caption"].split())
            attempt_prompt = (
                prompt
                + f"\nIMPORTANT: your previous caption was {wc} words — under the "
                "160-word floor and nowhere near the 170-240 target. Rewrite it "
                "with real detail: another • benefit line carrying a concrete "
                "number, and a two-sentence answer to the buyer objection. "
                "Same hook, same structure, more substance."
            )
    return last
