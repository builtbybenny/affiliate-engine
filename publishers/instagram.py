"""Instagram Graph API publisher (free, official).

Flow for each post type:
  • Image:    POST /media (image_url) -> POST /media_publish
  • Reel:     POST /media (media_type=REELS, video_url) -> poll -> publish
  • Carousel: POST /media per child (is_carousel_item=true) -> CAROUSEL parent -> publish

Media must be reachable at a public URL (we serve public/ via GitHub Pages or a tunnel).
"""
from __future__ import annotations

import time

import requests

from core import config

API = f"https://graph.facebook.com/{config.GRAPH_VERSION}"


class IGError(RuntimeError):
    pass


def _post(path: str, data: dict) -> dict:
    r = requests.post(f"{API}/{path}", data=data, timeout=60)
    payload = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
    if r.status_code >= 400:
        err = payload.get("error", {})
        raise IGError(f"{r.status_code} {err.get('type')}: {err.get('message')} (code {err.get('code')})")
    return payload


def _get(path: str, params: dict) -> dict:
    r = requests.get(f"{API}/{path}", params=params, timeout=60)
    payload = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
    if r.status_code >= 400:
        err = payload.get("error", {})
        raise IGError(f"{r.status_code} {err.get('type')}: {err.get('message')} (code {err.get('code')})")
    return payload


def publish_image(image_url: str, caption: str) -> str:
    if not config.IG_USER_ID or not config.ACCESS_TOKEN:
        raise IGError("IG_USER_ID / ACCESS_TOKEN missing. Run scripts/setup_tokens.py first.")
    base = {"access_token": config.ACCESS_TOKEN}
    c = _post(f"{config.IG_USER_ID}/media", {**base, "image_url": image_url, "caption": caption})
    pub = _post(f"{config.IG_USER_ID}/media_publish", {**base, "creation_id": c["id"]})
    return pub["id"]


def publish_carousel(image_urls: list[str], caption: str) -> str:
    if not 2 <= len(image_urls) <= 10:
        raise IGError("Carousel needs 2-10 images.")
    base = {"access_token": config.ACCESS_TOKEN}
    children: list[str] = []
    for url in image_urls:
        c = _post(
            f"{config.IG_USER_ID}/media",
            {**base, "image_url": url, "is_carousel_item": "true"},
        )
        children.append(c["id"])
    parent = _post(
        f"{config.IG_USER_ID}/media",
        {**base, "media_type": "CAROUSEL", "children": ",".join(children), "caption": caption},
    )
    _wait_ready(parent["id"])
    pub = _post(f"{config.IG_USER_ID}/media_publish", {**base, "creation_id": parent["id"]})
    return pub["id"]


def publish_reel(video_url: str, caption: str, share_to_feed: bool = True) -> str:
    base = {"access_token": config.ACCESS_TOKEN}
    c = _post(
        f"{config.IG_USER_ID}/media",
        {
            **base,
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true" if share_to_feed else "false",
        },
    )
    _wait_ready(c["id"])
    pub = _post(f"{config.IG_USER_ID}/media_publish", {**base, "creation_id": c["id"]})
    return pub["id"]


def post_first_comment(media_id: str, comment: str) -> str:
    """Requires instagram_business_manage_comments (IG Login) or
    instagram_manage_comments (FB Login). Best-effort: failures don't
    block publishing — hashtags stay in the caption as fallback."""
    try:
        res = _post(f"{media_id}/comments", {"message": comment})
        return res.get("id", "")
    except IGError as e:
        print(f"  (first-comment skipped: {e})")
        return ""


def _wait_ready(container_id: str, max_wait: int = 300) -> None:
    """Poll container status until FINISHED (docs: 1x/sec, max 5 min)."""
    deadline = time.time() + max_wait
    while time.time() < deadline:
        st = _get(container_id, {"fields": "status_code", "access_token": config.ACCESS_TOKEN})
        code = st.get("status_code")
        if code == "FINISHED":
            return
        if code in ("ERROR", "EXPIRED"):
            raise IGError(f"Container {container_id} entered {code}.")
        time.sleep(6)
    raise IGError(f"Container {container_id} not ready after {max_wait}s (status: {code}).")


def publishing_limit() -> dict:
    return _get(
        f"{config.IG_USER_ID}/content_publishing_limit",
        {"fields": "quota_total,quota_remaining", "access_token": config.ACCESS_TOKEN},
    )
