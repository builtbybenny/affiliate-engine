#!/usr/bin/env python3
"""Builds public/lists.html — permanent home of every lead-magnet list.

The link-bio page links here; impatient commenters get instant access,
and the DM/reply bot points to it as backup.
"""
from __future__ import annotations

import html
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console  # noqa: E402

setup_console()

from media.lead import load_lists  # noqa: E402

TEMPLATE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{brand} — the lists</title>
<style>
  :root {{ color-scheme: dark; }}
  body {{ margin:0; font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif;
         background:linear-gradient(180deg,#0f172a,#1e293b); color:#f8fafc;
         display:flex; justify-content:center; }}
  main {{ width:100%; max-width:560px; padding:40px 20px 80px; }}
  h1 {{ font-size:1.5rem; margin:.2em 0; text-align:center; }}
  p.sub {{ color:#94a3b8; margin-top:0; text-align:center; }}
  h2 {{ font-size:1.05rem; margin-top:36px; color:{accent}; }}
  .kw {{ display:inline-block; padding:2px 10px; border-radius:999px;
        background:{accent}; color:#0b1020; font-weight:700; font-size:.75rem; }}
  li {{ margin:10px 0; }}
  a {{ color:{accent}; text-decoration:none; font-weight:600; }}
  .desc {{ color:#cbd5e1; font-weight:400; }}
  footer {{ margin-top:48px; color:#64748b; font-size:.8rem; text-align:center; }}
</style>
</head>
<body>
<main>
  <h1>{brand}</h1>
  <p class="sub">Every list we promised in the posts. Bookmarked forever.</p>
  {sections}
  <footer>Found this from a post? Comment the keyword on the latest one and
  we'll DM you new lists as they drop.</footer>
</main>
</body>
</html>
"""


def main() -> None:
    data = load_lists()
    sections = []
    for list_id, spec in data.items():
        items = "".join(
            f'<li><a href="{html.escape(i["url"])}" rel="nofollow" target="_blank">{html.escape(i["name"])}</a>'
            f' <span class="desc">— {html.escape(i["desc"])}</span></li>'
            for i in spec["items"]
        )
        sections.append(
            f'<h2>{html.escape(spec["title"])} <span class="kw">comment "{html.escape(spec["keyword"])}"</span></h2>'
            f'<ul>{items}</ul>'
        )
    page = TEMPLATE.format(
        brand=html.escape("Stack & Save"),
        sections="\n".join(sections),
        accent="#38bdf8",
    )
    out = Path("public") / "lists.html"
    out.write_text(page, encoding="utf-8")
    print(f"Wrote {out.resolve()} with {len(data)} lists.")


if __name__ == "__main__":
    main()
