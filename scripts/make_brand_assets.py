#!/usr/bin/env python3
"""Create the IG/FB profile picture + link-bio social card.

Renders public/brand/avatar.png (1024x1024) and public/brand/social_card.png
(1080x1350, for FB Page cover-adjacent posts) from the locked brand:
  • "S&S" monogram tile with gradient + accent ring
Free, instant, no design skills. Rerun anytime: python scripts/make_brand_assets.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console  # noqa: E402

setup_console()

from core import config  # noqa: E402
from media import common  # noqa: E402

AVATAR = 1024
CARD_W, CARD_H = 1080, 1350
COVER_W, COVER_H = 851, 315  # Facebook Page cover, exact desktop size


def monogram_tile(size: int, palette: tuple[str, str, str, str]) -> "object":
    top, bottom, accent, text = palette
    img = common.vertical_gradient((size, size), top, bottom)
    d = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(img, "RGBA")
    acc = common.hex_to_rgb(accent)

    # accent ring
    m = int(size * 0.06)
    d.ellipse((m, m, size - m, size - m), outline=(*acc, 255), width=int(size * 0.03))

    # monogram
    f = common.font(int(size * 0.42), bold=True)
    label = "S&S"
    w = f.getlength(label)
    d.text(((size - w) / 2, size / 2 - size * 0.26), label, font=f, fill=(255, 255, 255, 255))
    return img


def main() -> None:
    out = config.PUBLIC_DIR / "brand"
    out.mkdir(parents=True, exist_ok=True)
    palette = config.PALETTES[0]

    avatar = monogram_tile(AVATAR, palette)
    avatar.convert("RGB").save(out / "avatar.png")

    # social card: tile + brand name + handle
    card = common.vertical_gradient((CARD_W, CARD_H), palette[0], palette[1])
    tile = monogram_tile(560, palette)
    card.paste(tile, (260, 210))
    d = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(card, "RGBA")
    f1 = common.font(96, bold=True)
    f2 = common.font(52, bold=True)
    d.text(((CARD_W - f1.getlength(config.BRAND_NAME)) / 2, 880), config.BRAND_NAME, font=f1, fill=(255, 255, 255, 255))
    d.text(((CARD_W - f2.getlength(config.BRAND_HANDLE)) / 2, 1010), config.BRAND_HANDLE, font=f2, fill=(*common.hex_to_rgb(palette[2]), 255))
    d.text(((CARD_W - f2.getlength("SaaS tools · free trials · honest stacks")) / 2, 1100),
           "SaaS tools · free trials · honest stacks", font=common.font(40, bold=False), fill=(255, 255, 255, 210))
    card.convert("RGB").save(out / "social_card.png")

    # Facebook Page cover banner: monogram left, name + handle + tagline right
    cover = common.vertical_gradient((COVER_W, COVER_H), palette[0], palette[1])
    d = __import__("PIL.ImageDraw", fromlist=["ImageDraw"]).Draw(cover, "RGBA")
    tile = monogram_tile(220, palette)
    cover.paste(tile, (44, 48))
    acc = common.hex_to_rgb(palette[2])
    x = 316
    f1 = common.font(62, bold=True, weight="black")
    d.text((x, 84), config.BRAND_NAME, font=f1, fill=(255, 255, 255, 255))
    f2 = common.font(34, bold=True)
    d.text((x, 168), config.BRAND_HANDLE, font=f2, fill=(*acc, 255))
    f3 = common.font(28, bold=False)
    d.text((x, 220), "SaaS tools - free trials - honest stacks", font=f3, fill=(255, 255, 255, 215))
    cover.convert("RGB").save(out / "fb_cover.png")

    print(f"Wrote avatar.png, social_card.png, fb_cover.png in {out}")


if __name__ == "__main__":
    main()
