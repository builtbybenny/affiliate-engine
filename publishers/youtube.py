"""YouTube Shorts publisher (free, official API).

Flow:
  • scripts/setup_youtube_tokens.py → data/yt_token.enc (Fernet, same key as Meta's)
  • publishers/youtube.py           → videos.insert (resumable) with the reel MP4
  • Shorts = 1080×1920 vertical + ≤3 min; auto-classified by YouTube,
    no special metadata required.

Offline CI: GOOGLE_OAUTH_TOKEN_JSON env var (optional) carries the same
credential JSON you'd otherwise only have locally.
"""
from __future__ import annotations

import json
import os
from typing import Any

from core import config

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
YT_TOKEN_ENC = config.DATA_DIR / "yt_token.enc"


class YTError(RuntimeError):
    pass


def _stored_json() -> dict:
    """Credential dict from the encrypted store, or GOOGLE_OAUTH_TOKEN_JSON env."""
    raw = ""
    env = os.getenv("GOOGLE_OAUTH_TOKEN_JSON", "").strip()
    if env:
        raw = env
    elif YT_TOKEN_ENC.exists():
        if not config.TOKEN_ENCRYPTION_KEY:
            raise YTError("TOKEN_ENCRYPTION_KEY missing — cannot decrypt yt_token.enc")
        from core.cryptoutil import decrypt_from_file

        raw = decrypt_from_file(YT_TOKEN_ENC, config.TOKEN_ENCRYPTION_KEY)
    return json.loads(raw) if raw else {}


def _save_creds(creds: Any) -> None:
    payload = {
        "token": creds.token,
        "refresh_token": creds.refresh_token,
        "client_id": creds.client_id,
        "client_secret": creds.client_secret,
    }
    if not config.TOKEN_ENCRYPTION_KEY or not os.environ.get("SAVE_YT_TOKEN"):
        return  # local interactive flow already keeps the file fresh
    from core.cryptoutil import encrypt_to_file

    encrypt_to_file(
        json.dumps(payload), YT_TOKEN_ENC, config.TOKEN_ENCRYPTION_KEY
    )


def _service() -> Any:
    """Build the youtube client from stored creds; refresh transparently."""
    from googleapiclient.discovery import build
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    tok = _stored_json()
    if not tok:
        raise YTError(
            "No YouTube credentials. Run scripts/setup_youtube_tokens.py "
            "(interactive, opens a browser) or set GOOGLE_OAUTH_TOKEN_JSON."
        )
    creds = Credentials(
        token=tok.get("token"),
        refresh_token=tok.get("refresh_token"),
        token_uri="https://oauth2.googleapis.com/token",
        client_id=tok.get("client_id"),
        client_secret=tok.get("client_secret"),
        scopes=SCOPES,
    )
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_creds(creds)
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def publish_short(mp4_path: str, caption: str) -> str:
    """Upload ≤3-min vertical MP4 as a YouTube Short. Returns video id.

    caption is 'title\\n\\ndescription' (caller decides); hashtags ride in
    the description, never the title.
    """
    from googleapiclient.http import MediaFileUpload

    title, _, body = caption.partition("\n\n")
    body = body if body.strip() else "Link in bio — full stack breakdown inside."
    yt = _service()
    media = MediaFileUpload(
        mp4_path, mimetype="video/mp4", chunksize=1024 * 1024, resumable=True
    )
    request = yt.videos().insert(
        part="snippet,status",
        body={
            "snippet": {
                "title": title.strip()[:100],
                "description": body.strip(),
                "categoryId": "22",  # People & Blogs
                "selfDeclaredMadeForKids": False,
            },
            "status": {"privacyStatus": "public"},
        },
        media_body=media,
    )
    response: dict | None = None
    last_err: Exception | None = None
    retries = 3
    while response is None:
        try:
            status, response = request.next_chunk()
            last_err = None
        except Exception as e:  # transient network errors
            last_err = e
            retries -= 1
            if retries <= 0:
                raise YTError(f"YouTube upload failed: {e}") from e
    if last_err is None and response.get("state") == "ERROR":
        raise YTError("YouTube rejected the upload chunk")
    return response["id"]
