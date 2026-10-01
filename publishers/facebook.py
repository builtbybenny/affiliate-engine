"""Facebook Page publisher (free, official Graph API).

Cross-posting strategy: the same product becomes a native FB post.
  • Carousel days -> FB photo post (first slide) + link in message
  • Reel days     -> FB video post (reel renders natively in feed)
Link posts are used when you want the click to happen right on Facebook.
"""
from __future__ import annotations

import requests

from core import config

API = f"https://graph.facebook.com/{config.GRAPH_VERSION}"


class FBError(RuntimeError):
    pass


def _post(path: str, data: dict) -> dict:
    data = {**data, "access_token": config.ACCESS_TOKEN}
    r = requests.post(f"{API}/{path}", data=data, timeout=120)
    payload = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
    if r.status_code >= 400:
        err = payload.get("error", {})
        raise FBError(f"{r.status_code} {err.get('type')}: {err.get('message')} (code {err.get('code')})")
    return payload


def publish_photo(image_url: str, message: str) -> str:
    if not config.FB_PAGE_ID or not config.ACCESS_TOKEN:
        raise FBError("FB_PAGE_ID / ACCESS_TOKEN missing. Run scripts/setup_tokens.py first.")
    res = _post(f"{config.FB_PAGE_ID}/photos", {"url": image_url, "caption": message})
    return res["post_id"] if "post_id" in res else res.get("id", "")


def publish_video(video_url: str, description: str) -> str:
    res = _post(f"{config.FB_PAGE_ID}/videos", {"file_url": video_url, "description": description})
    return res.get("id", "")


def publish_link(link: str, message: str) -> str:
    res = _post(f"{config.FB_PAGE_ID}/feed", {"link": link, "message": message})
    return res.get("id", "")
