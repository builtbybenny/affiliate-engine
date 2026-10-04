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
import time

import requests

from core import config
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
    "everyday situation they solve."
)


def write_copy(product: dict, theme: str, fallback_hooks: list[str],
               fallback_slides: list[str], fallback_caption: str,
               hook_ideas: list[str] | None = None) -> dict | None:
    """Returns {'hook': str, 'slides': [..], 'caption': str} or None on any failure.

    hook_ideas: internet-researched hook strings for THIS product
    (core/hooklib.pick). When present, the model must open with one of
    their structures instead of reaching for the same generic angles.
    """
    if not available():
        return None
    trial = (product.get("trial") or "").strip()
    ideas_block = ""
    if hook_ideas:
        ideas = "\n".join(f"- {i}" for i in hook_ideas[:5])
        ideas_block = (
            "\nRESEARCHED HOOKS (proven click-structures for this product — "
            "the hook MUST use one of these structures, rewritten to fit "
            "this tool's specifics; do not invent a different angle):\n"
            f"{ideas}\n"
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
        f"{ideas_block}\n"
        "SCROLLER-FIRST STRUCTURE:\n"
        + (
            '- "hook": open with the researched hook structure you chose, '
            "compressed to max 9 words, curiosity/number/pain-led.\n"
            if hook_ideas else
            '- "hook": the human moment (pain/cost/chaos the scroller recognizes) '
            "in plain words; do NOT put the tool or competitor name in the hook.\n"
        )
        + "- Slides: first 1-2 slides deepen the human moment or the old painful "
        "way WITHOUT assuming the scroller knows the category; middle slides "
        "reveal the tool as the fix with one concrete benefit each; last "
        "slide = free-trial CTA.\n"
        '- "caption" line 1: the human moment again, no tool name. The literal '
        f"product name '{product['name']}' MUST appear in the caption body "
        "(one middle line introduces it as the fix — never leave the reader "
        "without the name). Never name the competitor in the caption.\n\n"
        "Return STRICT JSON with keys:\n"
        '  "hook": slide-1 headline, max 9 words, curiosity or number-led;\n'
        '  "slides": 3-5 strings, max 8 words each, one benefit or proof point per slide;\n'
        '  "caption": 60-120 words. Line 1 = hook rephrase. Then 2-4 short lines '
        "with one benefit each using the bullet char •. Then one CTA line about "
        f"the free trial{' (' + trial + ')' if trial else ''}. "
        "End with: 'Affiliate link - we may earn a commission at no extra cost to you. #ad'\n"
        "No other keys. JSON only."
    )
    raw = _generate(prompt)
    if not raw:
        return None
    try:
        data = json.loads(raw)
        hook = str(data.get("hook", "")).strip()
        slides = [str(s).strip() for s in data.get("slides", []) if str(s).strip()]
        caption = str(data.get("caption", "")).strip()
        if not (hook and slides and caption):
            return None
        return {"hook": hook, "slides": slides[:5], "caption": caption[:2200]}
    except Exception:
        return None
