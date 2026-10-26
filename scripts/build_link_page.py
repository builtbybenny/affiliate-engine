#!/usr/bin/env python3
"""Build the link-in-bio page (public/index.html) from data/products.csv.

Deployed free via GitHub Pages — this URL goes in your IG/FB bios.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console; setup_console()
from core import config, planner

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<!-- Dub partner-profile domain verification (partners.dub.co). The github.io
     DNS is GitHub's, so the TXT-record route is impossible — Dub accepts the
     same token as a meta tag. Tokenized below; regenerate only if revoked. -->
<meta name="dub-domain-verification" content="{dub_token}">
<title>{brand} — links</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif;
         background: linear-gradient(180deg,#0f172a,#1e293b); color:#f8fafc;
         display:flex; justify-content:center; }}
  main {{ width:100%; max-width:520px; padding:40px 20px 80px; text-align:center; }}
  h1 {{ font-size:1.6rem; margin:.2em 0; }}
  p.sub {{ color:#94a3b8; margin-top:0; }}
  a.card {{ display:block; margin:14px 0; padding:18px 20px; border-radius:16px;
           background:rgba(255,255,255,.06); border:1px solid rgba(255,255,255,.12);
           color:#f8fafc; text-decoration:none; transition:transform .1s ease; }}
  a.card:hover {{ transform:translateY(-2px); background:rgba(255,255,255,.10); }}
  .name {{ font-weight:700; }}
  .badge {{ display:inline-block; margin-left:8px; padding:2px 10px; border-radius:999px;
           background:{accent}; color:#0b1020; font-size:.72rem; font-weight:700;
           vertical-align:middle; }}
  .price {{ color:{accent}; font-weight:700; margin-left:8px; }}
  .why {{ display:block; color:#cbd5e1; font-size:.9rem; margin-top:4px; }}
  footer {{ margin-top:36px; color:#64748b; font-size:.8rem; }}
</style>
</head>
<body>
<main>
  <h1>{brand}</h1>
  <p class="sub">{tagline}</p>
  {cards}
  <footer>Affiliate disclosure: we may earn a commission at no extra cost to you.</footer>
</main>
</body>
</html>
"""


# Links that are NOT in data/products.csv (user decision 2026-10-25).
# Writesonic: affiliate application submitted 2026-10-15, approval pending —
# until the referral link exists we point visitors at the pricing page and
# claim no commission (rel="nofollow sponsored" only; no offer language).
# On approval: swap `url` for the referral link (and move the row into
# products.csv so content can feature it). On refusal: delete this entry.
PENDING_LINKS = [
    {
        "name": "Writesonic",
        "url": "https://writesonic.com/pricing/agencies",
        "badge": "AI writing",
        "price": "",
        "why": "AI writing and SEO tools — see the agency plans",
    },
]


def _card(name: str, badge: str, price: str, why: str, url: str) -> str:
    return (
        f'<a class="card" href="{url}" rel="nofollow sponsored" target="_blank">'
        f'<span class="name">{name}</span>{badge}<span class="price">{price}</span>'
        f'<span class="why">{why}</span></a>'
    )


def main() -> None:
    products = planner.load_products()
    cards = []
    for p in products:
        name = html.escape(p["name"])
        price = html.escape(f"{p.get('currency','')} {p.get('price','')}".strip())
        why = html.escape((planner.parse_benefits(p) or [""])[0])
        url = html.escape(p.get("url") or "#")
        trial = (p.get("trial") or "").strip()
        badge = f'<span class="badge">{html.escape(trial[:24])}</span>' if trial else ""
        cards.append(_card(name, badge, price, why, url))
    for p in PENDING_LINKS:
        badge = (
            f'<span class="badge">{html.escape(str(p.get("badge", "")))}</span>'
            if p.get("badge") else ""
        )
        cards.append(_card(
            html.escape(str(p.get("name", ""))),
            badge,
            html.escape(str(p.get("price", ""))),
            html.escape(str(p.get("why", ""))),
            html.escape(str(p.get("url", "#"))),
        ))
    page = TEMPLATE.format(
        brand=html.escape(config.BRAND_NAME),
        dub_token="6091882d-7007-4988-b901-75498d9c9c53",
        tagline=html.escape("The exact stack I use — start every tool free"),
        cards="\n  ".join(cards),
        accent="#38bdf8",
    )
    config.PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    (config.PUBLIC_DIR / "index.html").write_text(page, encoding="utf-8")
    print(f"Wrote {config.PUBLIC_DIR / 'index.html'} with {len(cards)} product links.")


if __name__ == "__main__":
    main()
