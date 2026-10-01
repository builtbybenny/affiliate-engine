"""Discovers GitHub Pages, ngrok or cloudflared tunnels and returns the public media URL.

Instagram/Facebook fetch media from the URL you give them, so files in public/
must be reachable from the internet. This module figures that URL out for you.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from core import config


def _try_json(url: str) -> dict | None:
    try:
        import requests

        r = requests.get(url, timeout=5)
        if r.status_code == 200:
            return r.json()
    except Exception:
        pass
    return None


def tunnel_url_from_processes() -> str | None:
    """Reads the local tunnel process command lines (Windows + POSIX)."""
    try:
        if os.name == "nt":
            out = subprocess.run(
                ["wmic", "process", "where", "name like '%ngrok%' or name like '%cloudflared%'",
                 "get", "commandline"],
                capture_output=True, text=True, timeout=10,
            ).stdout
        else:
            out = subprocess.run(
                ["sh", "-c", "ps -eo args | grep -Ei 'ngrok|cloudflared' | grep -v grep"],
                capture_output=True, text=True, timeout=10,
            ).stdout
    except Exception:
        return None
    for token in out.split():
        if token.startswith("http") and "trycloudflare" in token:
            return token.rstrip()
    # ngrok local API (default port 4040)
    info = _try_json("http://127.0.0.1:4040/api/tunnels")
    if info:
        for t in info.get("tunnels", []):
            u = t.get("public_url", "")
            if u.startswith("https://"):
                return u
    return None


def resolve_public_base() -> str:
    """Priority: env var > GitHub Pages (docs/ branch or main) > running tunnel."""
    if config.PUBLIC_BASE_URL:
        return config.PUBLIC_BASE_URL

    # Try to discover the repo from git remote
    try:
        remote = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True, text=True, timeout=10,
        ).stdout.strip()
        if "github.com" in remote:
            slug = remote.split("github.com")[1].lstrip("/:").removesuffix(".git")
            api = f"https://api.github.com/repos/{slug}/pages"
            headers = {"Accept": "application/vnd.github+json"}
            try:
                import requests

                r = requests.get(api, headers=headers, timeout=5)
                if r.status_code == 200:
                    html = r.json().get("html_url", "").rstrip("/")
                    if html:
                        return f"{html}/docs"
            except Exception:
                pass
    except Exception:
        pass

    tun = tunnel_url_from_processes()
    if tun:
        return tun
    raise RuntimeError(
        "No public URL available. Set PUBLIC_MEDIA_BASE_URL in .env, push docs/ to "
        "GitHub Pages, or start a tunnel (ngrok http 8000 / cloudflared)."
    )


def media_url(rel_path: Path) -> str:
    """rel_path must be under public/. Returns absolute URL."""
    rel = rel_path.resolve().relative_to(config.PUBLIC_DIR.resolve()).as_posix()
    return f"{resolve_public_base()}/{rel}"
