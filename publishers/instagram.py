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


# Meta answers two ways when it is having a bad moment, and both have burnt
# scheduled runs: code 4 "Application request limit reached" (403) and code
# 9004 "Only photo or video can be accepted as media type" (400) while a
# container is still settling. Retrying those is safe — a failed container
# create / media_publish published nothing — whereas auth (190), permission
# (10/200) and quota errors must fail loudly instead of burning a window.
_TRANSIENT = (
    "application request limit reached",
    "(code 4)",
    "only photo or video",
    "(code 9004)",
    "try again later",
    "temporarily unavailable",
)


def _retryable(msg: str) -> bool:
    low = msg.lower()
    return any(t in low for t in _TRANSIENT)


def _raise(payload: dict, status: int) -> IGError:
    err = payload.get("error", {})
    return IGError(f"{status} {err.get('type')}: {err.get('message')} (code {err.get('code')})")


# Two different clocks, so two different ladders. A settling container
# (9004) clears in seconds, but an exhausted app quota (code 4) clears when
# the rolling hour moves — the old 15/30/60s ladder gave up after 105 seconds
# and turned one limited morning into three separate failed runs (2026-10-27
# and 2026-10-28), each of which then built a fresh set of containers into the
# same exhausted quota. Code 4 now waits minutes, not seconds.
_QUOTA_LADDER = (30, 120, 240, 300)      # ~11.5 min total
_CONTAINER_LADDER = (15, 30, 60)         # settling container / brief blip


def _is_quota(err: str) -> bool:
    low = err.lower()
    return "request limit" in low or "(code 4)" in low


def _ladder(err: str, default: tuple[int, ...]) -> tuple[int, ...]:
    return _QUOTA_LADDER if _is_quota(err) else default


def _post(path: str, data: dict, retries: tuple[int, ...] = _CONTAINER_LADDER) -> dict:
    """POST with bounded backoff; the ladder widens for an exhausted quota."""
    last: IGError | None = None
    plan: tuple[int, ...] = retries
    for attempt in range(len(plan) + 1):
        r = requests.post(f"{API}/{path}", data=data, timeout=60)
        payload = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
        if r.status_code < 400:
            return payload
        last = _raise(payload, r.status_code)
        if plan is retries:
            plan = _ladder(str(last), retries)
        if attempt < len(plan) and _retryable(str(last)):
            print(f"  (IG transient on {path}: {last}); retrying in {plan[attempt]}s")
            time.sleep(plan[attempt])
            continue
        raise last
    raise last or IGError(f"POST {path} failed")


def _get(path: str, params: dict, retries: tuple[int, ...] = (10, 25)) -> dict:
    """GET with the same backoff — status polling and quota checks hit code 4 too."""
    last: IGError | None = None
    plan: tuple[int, ...] = retries
    for attempt in range(len(plan) + 1):
        r = requests.get(f"{API}/{path}", params=params, timeout=60)
        payload = r.json() if r.headers.get("content-type", "").startswith("application/json") else {"raw": r.text}
        if r.status_code < 400:
            return payload
        last = _raise(payload, r.status_code)
        if plan is retries:
            plan = _ladder(str(last), retries)
        if attempt < len(plan) and _retryable(str(last)):
            print(f"  (IG transient on {path}: {last}); retrying in {plan[attempt]}s")
            time.sleep(plan[attempt])
            continue
        raise last
    raise last or IGError(f"GET {path} failed")


def ensure_available() -> None:
    """One cheap call before any container is created.

    Building a carousel costs one container per slide. Doing that while the
    app's request quota is already exhausted wastes the whole allowance and
    leaves orphan containers behind, so ask first and let the quota ladder
    wait it out. Failure here is fatal for this run — but it fails before
    spending anything.
    """
    if not config.IG_USER_ID or not config.ACCESS_TOKEN:
        raise IGError("IG_USER_ID / ACCESS_TOKEN missing. Run scripts/setup_tokens.py first.")
    _get(config.IG_USER_ID, {"fields": "username", "access_token": config.ACCESS_TOKEN})


def publish_image(image_url: str, caption: str) -> str:
    ensure_available()
    base = {"access_token": config.ACCESS_TOKEN}
    c = _post(f"{config.IG_USER_ID}/media", {**base, "image_url": image_url, "caption": caption})
    pub = _post(f"{config.IG_USER_ID}/media_publish", {**base, "creation_id": c["id"]})
    return pub["id"]


def publish_carousel(image_urls: list[str], caption: str) -> str:
    if not 2 <= len(image_urls) <= 10:
        raise IGError("Carousel needs 2-10 images.")
    ensure_available()
    base = {"access_token": config.ACCESS_TOKEN}
    children: list[str] = []
    for url in image_urls:
        c = _post(
            f"{config.IG_USER_ID}/media",
            {**base, "image_url": url, "is_carousel_item": "true"},
        )
        # Meta error 9004 ("Only photo or video can be accepted as media
        # type") fires on the parent creation while a child container is
        # still processing. Every scheduled morning-slot carousel failure
        # on 2026-10-12 (#45) and 2026-10-14 (#59) was this race; both
        # recovered only via a later trigger. Poll each child to FINISHED
        # (fast — seconds for images) and the parent reliably accepts.
        _wait_ready(c["id"], max_wait=120)
        children.append(c["id"])
    parent: dict | None = None
    last_err: IGError | None = None
    for delay in (0, 20, 45):
        if delay:
            time.sleep(delay)
        try:
            parent = _post(
                f"{config.IG_USER_ID}/media",
                {**base, "media_type": "CAROUSEL", "children": ",".join(children), "caption": caption},
            )
            break
        except IGError as e:
            # Retry ONLY the known-transient case; anything else is fatal.
            if "9004" in str(e) or "only photo or video" in str(e).lower():
                last_err = e
                continue
            raise
    if parent is None:
        raise last_err or IGError("carousel parent creation failed")
    _wait_ready(parent["id"])
    pub = _post(f"{config.IG_USER_ID}/media_publish", {**base, "creation_id": parent["id"]})
    return pub["id"]


def publish_reel(video_url: str, caption: str, share_to_feed: bool = True) -> str:
    ensure_available()
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
    block publishing — hashtags stay in the caption as fallback.

    Root cause of every silent failure (found 2026-10-07): this call used
    to omit access_token, and an unauthenticated Graph comment POST returns
    the misleading code 100 "Object ... does not exist, cannot be loaded
    due to missing permissions". The token was the whole bug; retries only
    cover the residual genuine indexing lag right after media_publish
    (~105s of max backoff — cheap insurance in CI)."""
    delays = (15, 30, 60)
    err = ""
    for i in range(len(delays) + 1):
        try:
            res = _post(f"{media_id}/comments", {"message": comment, "access_token": config.ACCESS_TOKEN})
            if i:
                print(f"  IG first comment posted on attempt {i + 1}")
            return res.get("id", "")
        except IGError as e:
            err = str(e)
            if i < len(delays):
                print(f"  (first-comment attempt {i + 1} failed: {err}); retrying in {delays[i]}s")
                time.sleep(delays[i])
    print(f"  (first-comment skipped after {len(delays) + 1} attempts: {err})")
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
