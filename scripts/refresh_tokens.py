#!/usr/bin/env python3
"""Token maintenance (usually NOT needed).

setup_tokens.py stores a *Page access token*, which never expires. This helper
is only for the rare case where you're using a User token: it exchanges it for
a 60-day long-lived token and updates .env.

Usage:
  python scripts/refresh_tokens.py            # refresh token currently in .env
  python scripts/refresh_tokens.py --token XX # refresh a specific token
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console; setup_console()
from core import config

API = f"https://graph.facebook.com/{config.GRAPH_VERSION}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--token", default="")
    args = ap.parse_args()

    app_id = (
        input("App ID (developers.facebook.com > App Settings > Basic) [Enter = use .env]: ").strip()
        or os.getenv("META_APP_ID", "")
    )
    app_secret = input("App Secret [Enter = use .env]: ").strip() or os.getenv("META_APP_SECRET", "")
    if not app_id or not app_secret:
        raise SystemExit("No App ID/secret available (not typed and not in .env as META_APP_ID/META_APP_SECRET).")
    token = args.token or config.ACCESS_TOKEN
    if not token:
        raise SystemExit("No token in .env and none supplied.")

    r = requests.get(
        f"{API}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": token,
        },
        timeout=30,
    ).json()
    if "access_token" not in r:
        raise SystemExit(f"Refresh failed: {r}")

    long_lived = r["access_token"]
    env_path = config.ROOT / ".env"
    lines = [
        l for l in env_path.read_text(encoding="utf-8").splitlines()
        if not l.startswith("ACCESS_TOKEN=")
    ]
    lines.append(f"ACCESS_TOKEN={long_lived}")
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Updated .env with a 60-day long-lived token.")
    print("TIP: run scripts/setup_tokens.py to switch to a never-expiring Page token.")


if __name__ == "__main__":
    main()
