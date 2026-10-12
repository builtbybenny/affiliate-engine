"""One-time YouTube OAuth setup — opens a browser, stores the token encrypted.

Usage:
    set YOUTUBE_CLIENT_SECRETS=C:\path\to\client_secret_xxx.json
    python scripts/setup_youtube_tokens.py

Steps it performs:
  1. Loads your Google Cloud OAuth client JSON (Desktop app type).
  2. Runs the InstalledAppFlow consent at localhost:8788.
  3. Saves access + refresh token to data/yt_token.enc
     (Fernet key = TOKEN_ENCRYPTION_KEY from .env — the same key CI uses).
"""
from __future__ import annotations

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core import config  # noqa: E402
from publishers.youtube import SCOPES, YT_TOKEN_ENC  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8788)
    args = ap.parse_args()

    secrets = os.getenv("YOUTUBE_CLIENT_SECRETS", "").strip()
    if not secrets or not os.path.exists(secrets):
        sys.exit(
            "Set YOUTUBE_CLIENT_SECRETS to your OAuth client JSON path first.\n"
            "Google Cloud Console → APIs & Services → Credentials → "
            "OAuth client ID (Desktop app) → download JSON."
        )
    key = config.TOKEN_ENCRYPTION_KEY
    if not key:
        sys.exit("TOKEN_ENCRYPTION_KEY missing in .env — generate one with "
                 "`python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\"`")

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(secrets, SCOPES)
    creds = flow.run_local_server(port=args.port, prompt="consent")

    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }
    from core.cryptoutil import encrypt_to_file

    encrypt_to_file(json.dumps(payload), YT_TOKEN_ENC, key)
    print(f"✅ YouTube token saved → {YT_TOKEN_ENC}")
    print("Publishing reels as Shorts is now wired — 'publish.py --yt-only' will work.")


if __name__ == "__main__":
    main()
