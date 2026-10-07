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

import requests

from core import config, copywriter
from core.boot import setup_console

setup_console()

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
    "beat adjectives. Keep hook lines under 10 words."
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


def _fit_caption(caption: str) -> str:
    """Keep the caption inside IG's 2,200-char cap with room for the folded
    hashtag block (~90 chars), and guarantee the canonical disclosure line.
    Cuts at a line boundary — never mid-sentence."""
    text = _reflow((caption or "").strip())
    # Research provenance is grounding for the writer, not copy for the
    # viewer — it leaked into live captions (2026-10-06/07 reels) and the
    # caption .txt files are public on Pages. Strip it here, at generation.
    text = re.sub(r"\s*\((?:source|src):\s*[^)]*\)", "", text, flags=re.IGNORECASE)
    text = text.replace("link below", "link in bio")  # reels link lives in bio
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


def write_copy(product: dict, theme: str, fallback_hooks: list[str],
               fallback_slides: list[str], fallback_caption: str,
               brief: dict | None = None) -> dict | None:
    """Returns {'hook': str, 'slides': [..], 'caption': str} or None on any failure.

    brief: per-product research brief (core/briefs) — search keywords real
    people use, attributable blog facts, buyer objections, pain-led angles.
    Without it the model writes from product data alone.

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
        f"{research_block}\n"
        "RETENTION RULES (skip rate decides distribution — first 3 seconds are "
        "the whole game):\n"
        "- The hook is a PROMISE the first on-screen scene repays immediately; "
        "it must be readable with sound off in one glance (max 9 words).\n"
        "- Specificity beats drama: numbers, dollars, minutes, before/after gaps. "
        "A hook that fits 10 different tools is dead.\n"
        "- Never open with the product or brand name — the frame already shows it. "
        "Pain first, tool as the answer. Never a soft question.\n"
        "- No intro energy: no 'hey', no context-setting, no 'in this post'.\n\n"
        "SCROLLER-FIRST STRUCTURE:\n"
        '- "hook_options": 4 candidate hooks — each a statement under 10 words, '
        "each seeded from the researched angles where they fit, each with "
        '"score": 0-100 for how likely it survives the first 3 seconds '
        "(reward: a number, immediate problem recognition, a concrete cost; "
        "punish: vagueness, tool-name openings, anything a competitor could say).\n"
        '- "hook": your single best pick from hook_options;\n'
        "- Slides: first 1-2 slides deepen the human moment the hook opened; "
        "middle slides reveal the tool as the fix with one concrete benefit each; "
        "last slide = free-trial CTA.\n\n"
        "SEO CAPTION SPEC (detailed — this caption is meant to rank in IG + "
        "Google search):\n"
        "- 170-240 words.\n"
        "- Line 1: a primary search phrase woven into the hook statement — an "
        "absolute claim, never a question, never tool-name-first. The primary "
        "search phrase must appear within the first two lines. The literal "
        f"product name '{product['name']}' MUST appear in the body (one middle "
        "line introduces it as the fix). Never name the competitor.\n"
        "- Never invent trial lengths, discounts, promo codes, or prices — use "
        "only the Free trial / Price values given above.\n"
        "- The caption MUST use literal line breaks: 5-7 separate lines, one "
        "thought per line, each • bullet on its own line — never one paragraph.\n"
        "- Body: 3-5 short lines. Repeat the primary keyword phrase naturally "
        "2 more times and one secondary phrase. Cite 2 researched facts with "
        "their short source note. Benefits as • lines with real numbers.\n"
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
        "- Exactly ONE specific engagement question after line 1 (references this "
        "content, e.g. which benefit they'd use first) — comments are a ranking "
        "signal.\n"
        f"- One CTA line about the free trial{' (' + trial + ')' if trial else ''}.\n"
        "- Do NOT write the affiliate disclosure — it is appended automatically.\n\n"
        "Return STRICT JSON with keys: hook_options (4 objects), hook, slides "
        "(3-5 strings, max 8 words each), caption. No other keys. JSON only."
    )
    def _parse(raw: str) -> dict | None:
        data = json.loads(raw)
        options = data.get("hook_options") or []
        hook = pick_retention_hook(options, str(data.get("hook", "")))
        slides = [str(s).strip() for s in data.get("slides", []) if str(s).strip()]
        caption = _fit_caption(str(data.get("caption", "")))
        if not (hook and slides and caption):
            return None
        return {"hook": hook, "slides": slides[:5], "caption": caption}

    # Models undershoot length targets; one bounded retry (2026-10-05 the
    # user picked max-detail captions — 130 words was consistently short).
    attempt_prompt = prompt
    last: dict | None = None
    for _ in range(2):
        raw = _generate(attempt_prompt)
        if not raw:
            return None
        try:
            out = _parse(raw)
        except Exception:
            return None
        if out and len(out["caption"].split()) >= 160:
            return out
        if out:
            last = out  # usable but short — retry once for more detail
            out = None
        attempt_prompt = (
            prompt
            + "\nIMPORTANT: your previous caption was under 160 words — too short "
            "for this spec. Hit 170-240 words: add another • benefit line with a "
            "real number, and give the objection answer two sentences of detail."
        )
    return last
