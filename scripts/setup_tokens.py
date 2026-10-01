#!/usr/bin/env python3
"""One-time setup wizard for the Meta token plumbing. Zero cost.

What it does:
  1. Takes a short-lived User Access Token you generate free at
     https://developers.facebook.com/tools/explorer (select your app +
     pages_show_list, pages_read_engagement, instagram_basic,
     instagram_content_publish, business_management).
  2. Exchanges it for a LONG-LIVED user token (needs App ID + App secret
     from developers.facebook.com -> your app -> Settings -> Basic).
  3. Uses the long-lived token on /me/accounts, which yields a
     NEVER-EXPIRING Page access token.
  4. Resolves your FB Page ID + Instagram professional account ID and
     writes IG_USER_ID / FB_PAGE_ID / ACCESS_TOKEN (plus META_APP_ID /
     META_APP_SECRET) into .env.
  5. Optionally (--encrypt) encrypts the token into data/token.enc for
     GitHub Actions.

Non-interactive use:
  python scripts/setup_tokens.py --token "EAAG..." --page "Stack & Save" \
      --app-id 123456 --app-secret abcd [--encrypt]

Interactive use (no flags) still works exactly as before.

Free forever: Page tokens obtained from a long-lived user token do not expire.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console; setup_console()
from core import config, cryptoutil

API = f"https://graph.facebook.com/{config.GRAPH_VERSION}"


def die(msg: str):
    raise SystemExit(f"ERROR: {msg}")


def encrypt_step(page_token: str) -> None:
    key = cryptoutil.generate_key()
    cryptoutil.encrypt_to_file(page_token, config.TOKEN_ENC, key)
    print(f"   Encrypted token -> {config.TOKEN_ENC}")
    print(f"   Add this Fernet key as GitHub secret TOKEN_KEY:\n   {key}")


def exchange_long_lived(short_token: str, app_id: str, app_secret: str) -> str:
    """Short-lived user token -> long-lived user token (~60 days), which is
    required so the Page token we derive afterwards never expires."""
    r = requests.get(
        f"{API}/oauth/access_token",
        params={
            "grant_type": "fb_exchange_token",
            "client_id": app_id,
            "client_secret": app_secret,
            "fb_exchange_token": short_token,
        },
        timeout=30,
    )
    data = r.json()
    if "access_token" not in data:
        die(
            "Token exchange failed: "
            + str(data.get("error", {}).get("message", data))
            + "\n(Check App ID + App secret, and that the token was pasted whole.)"
        )
    return data["access_token"]


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Meta token setup wizard (free, official Graph API)"
    )
    ap.add_argument("--token", help="short-lived user access token (skips the paste prompt)")
    ap.add_argument("--page", help='Page name or part of it to pick automatically, e.g. "Stack & Save"')
    ap.add_argument("--app-id", help="App ID from Settings -> Basic (else read from .env / prompt)")
    ap.add_argument("--app-secret", help="App secret from Settings -> Basic (else read from .env / prompt)")
    ap.add_argument("--encrypt", action="store_true", help="also encrypt the token for GitHub Actions")
    cli = ap.parse_args()

    print("=" * 64)
    print(" Meta token setup wizard (free, official Graph API)")
    print("=" * 64)

    short = (
        cli.token
        or input(
            "\n1) Go to https://developers.facebook.com/tools/explorer\n"
            "   - Select your App\n"
            "   - Add permissions: pages_show_list, pages_read_engagement,\n"
            "     instagram_basic, instagram_content_publish, business_management\n"
            "   - Generate Access Token and paste it here:\n> "
        ).strip()
    )
    if not short:
        die("No token entered.")

    app_id = cli.app_id or os.getenv("META_APP_ID", "")
    app_secret = cli.app_secret or os.getenv("META_APP_SECRET", "")
    if not app_id:
        app_id = input(
            "\nPaste your App ID (developers.facebook.com -> My Apps ->\n"
            "Stack & Save Engine -> Settings -> Basic):\n> "
        ).strip()
    if not app_secret:
        app_secret = input("\nPaste your App secret (same page, click Show):\n> ").strip()
    if not app_id or not app_secret:
        die("App ID and App secret are required so the token never expires.")

    # 1. Short-lived user token -> long-lived user token
    long_token = exchange_long_lived(short, app_id, app_secret)
    print("\n1) Exchanged short-lived token for a long-lived token (60 days).")

    # 2. List pages with the long-lived token -> page tokens never expire
    r = requests.get(f"{API}/me/accounts", params={"access_token": long_token}, timeout=30)
    resp = r.json()
    if "error" in resp:
        die("Graph API said: " + str(resp["error"].get("message", resp["error"])))
    pages = resp.get("data", [])
    if not pages:
        die("No Facebook Pages found for this token. Create a FB Page first.")

    if cli.page:
        matches = [i for i, p in enumerate(pages) if cli.page.lower() in p["name"].lower()]
        if not matches:
            die(
                f"No Page matching {cli.page!r}. Pages found: "
                + ", ".join(f"{p['name']} (id {p['id']})" for p in pages)
            )
        idx = matches[0]
        print(f"2) Auto-picked Page [{idx}] {pages[idx]['name']} (id {pages[idx]['id']})")
    else:
        print("\n2) Your Facebook Pages (never-expiring page tokens ready):")
        for i, p in enumerate(pages):
            print(f"   [{i}] {p['name']}  (id {p['id']})")
        idx = int(input("   Pick page number: ").strip() or 0)
    page = pages[idx]
    page_token, page_id = page["access_token"], page["id"]

    # 3. Instagram professional account linked to that page
    r = requests.get(
        f"{API}/{page_id}",
        params={"fields": "instagram_business_account", "access_token": page_token},
        timeout=30,
    ).json()
    ig = (r.get("instagram_business_account") or {}).get("id")
    if not ig:
        die(
            "This Page has no Instagram professional account connected.\n"
            "In Instagram app: Settings > Business tools > Connect a Facebook Page."
        )

    me = requests.get(
        f"{API}/{ig}", params={"fields": "username", "access_token": page_token}, timeout=30
    ).json()
    print(f"\n3) Connected: IG @{me.get('username')} (id {ig}) via Page '{page['name']}'")

    # 4. Write .env
    env_path = config.ROOT / ".env"
    lines = []
    if env_path.exists():
        lines = [
            l for l in env_path.read_text(encoding="utf-8").splitlines()
            if not l.startswith(
                ("IG_USER_ID=", "FB_PAGE_ID=", "ACCESS_TOKEN=", "META_APP_ID=", "META_APP_SECRET=")
            )
        ]
    lines += [
        f"IG_USER_ID={ig}",
        f"FB_PAGE_ID={page_id}",
        f"ACCESS_TOKEN={page_token}",
        f"META_APP_ID={app_id}",
        f"META_APP_SECRET={app_secret}",
    ]
    env_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"4) Wrote credentials to {env_path}")

    # 5. Optional: encrypted token for GitHub Actions
    if cli.encrypt:
        encrypt_step(page_token)
    elif not cli.token:
        if input("\n5) Encrypt token for CI? (y/N): ").strip().lower().startswith("y"):
            encrypt_step(page_token)

    print("\nDone. Next: python scripts/generate.py --today, then scripts/publish.py --today")


if __name__ == "__main__":
    main()
