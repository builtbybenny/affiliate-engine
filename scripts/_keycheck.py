#!/usr/bin/env python3
"""Ground-truth check of optional AI/stock keys. Writes data/_keycheck.json.

Never prints secrets. Verifies: .env loads, GEMINI_API_KEY works (live),
PEXELS_API_KEY works (live). Exit code is always 0; the JSON is the truth.
"""
import json
import os
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console  # noqa: E402

setup_console()

OUT = Path(__file__).resolve().parent.parent / "data" / "_keycheck.json"
out: dict = {"error": ""}

try:
    from dotenv import load_dotenv

    from core import config

    load_dotenv(config.ROOT / ".env")

    env_file = config.ROOT / ".env"
    out["env_file_exists"] = env_file.exists()
    out["env_bytes"] = env_file.stat().st_size if env_file.exists() else 0
    out["gitignore_covers_env"] = ".env" in (config.ROOT / ".gitignore").read_text(encoding="utf-8")

    # --- Gemini live test (uses self-healing model resolution from core.llm) ---
    gem = os.getenv("GEMINI_API_KEY", "").strip()
    out["gemini_key_present"] = bool(gem)
    out["gemini_key_len"] = len(gem)
    if gem:
        try:
            import requests

            from core import llm

            # Ground truth: what models does this key actually see?
            lm = requests.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": gem, "pageSize": 50},
                timeout=30,
            )
            out["listmodels_status"] = lm.status_code
            usable = []
            if lm.status_code == 200:
                for m in lm.json().get("models", []):
                    methods = m.get("supportedGenerationMethods", [])
                    if "generateContent" in methods:
                        usable.append(m.get("name", ""))
            out["usable_models"] = usable[:25]

            # Per-candidate probe with real payload, recording raw errors
            probes = {}
            for name in llm._MODEL_CANDIDATES:
                r = requests.post(
                    f"https://generativelanguage.googleapis.com/v1beta/models/{name}:generateContent",
                    params={"key": gem},
                    json={
                        "contents": [{"parts": [{"text": "Say OK."}]}],
                        "generationConfig": {"maxOutputTokens": 2000},
                    },
                    timeout=60,
                )
                entry = {"status": r.status_code}
                if r.status_code == 200:
                    try:
                        cand = r.json()["candidates"][0]
                        entry["text"] = "".join(
                            p.get("text", "") for p in cand.get("content", {}).get("parts", [])
                        )[:60]
                    except Exception:
                        entry["text"] = "(200 but no text)"
                else:
                    entry["err"] = r.text[:200]
                probes[name] = entry
            out["model_probes"] = probes

            model = llm.resolve_model()
            out["gemini_model"] = model or "(none answered)"
            raw = llm._generate('Reply with STRICT JSON {"ok": true} only.', max_tokens=2400)
            out["gemini_live_ok"] = bool(raw) and "ok" in raw.lower()
            if not out["gemini_live_ok"]:
                out["gemini_error"] = "generate returned empty — see gemini_model"
        except Exception as e:
            out["gemini_live_ok"] = False
            out["gemini_error"] = repr(e)[:300]

    # --- Pexels live test ---
    pex = os.getenv("PEXELS_API_KEY", "").strip()
    out["pexels_key_present"] = bool(pex)
    out["pexels_key_len"] = len(pex)
    if pex:
        try:
            import requests

            r = requests.get(
                "https://api.pexels.com/v1/search",
                params={"query": "modern workspace laptop", "per_page": 2, "orientation": "portrait"},
                headers={"Authorization": pex},
                timeout=30,
            )
            out["pexels_status"] = r.status_code
            if r.status_code == 200:
                photos = r.json().get("photos") or []
                out["pexels_results"] = len(photos)
                out["pexels_live_ok"] = len(photos) > 0
            else:
                out["pexels_live_ok"] = False
                out["pexels_error"] = r.text[:300]
        except Exception as e:
            out["pexels_live_ok"] = False
            out["pexels_error"] = repr(e)[:300]

    out["all_ok"] = bool(out.get("gemini_live_ok")) and bool(out.get("pexels_live_ok")) and out["env_file_exists"]

except Exception:
    out["error"] = traceback.format_exc()[-1500:]
    out["all_ok"] = False

OUT.write_text(json.dumps(out, indent=2), encoding="utf-8")
sys.exit(0)
