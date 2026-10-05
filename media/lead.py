"""Lead-magnet carousel: 'X free things that feel illegal to know' + comment CTA.

Unlike product carousels, these rotate through LIST ITEMS from
data/lead_lists.json and end on a 'comment KEYWORD' slide that drives the
engagement loop (auto-served by scripts/reply_bot.py).
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw

from core import config
from media import common

LEAD_LISTS = config.DATA_DIR / "lead_lists.json"


def load_lists() -> dict:
    if not LEAD_LISTS.exists():
        raise SystemExit(f"Missing {LEAD_LISTS}")
    return json.loads(LEAD_LISTS.read_text(encoding="utf-8"))


def _hook_slide(
    title: str, subtitle: str, keyword: str, palette: tuple, rng,
    bg_img: Image.Image | None = None,
) -> Image.Image:
    W, H = 1080, 1350
    top, bottom, accent_hex, _ = palette
    accent = common.hex_to_rgb(accent_hex)
    if bg_img is not None:
        base = common.vivid(common.cover_crop(bg_img, W, H)).convert("RGBA")
        base = Image.alpha_composite(base, Image.new("RGBA", base.size, (0, 0, 0, 110)))
    else:
        base = common.vivid(common.vertical_gradient((W, H), top, bottom)).convert("RGBA")
        # accent blobs only on the gradient path (they fight with photos)
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d2 = ImageDraw.Draw(layer)
        d2.ellipse((W * 0.5, -H * 0.1, W * 1.3, H * 0.3), fill=common.with_alpha(accent, 40))
        base.alpha_composite(layer)
    draw = ImageDraw.Draw(base, "RGBA")

    _brand_chip(draw, palette)
    common.draw_fitted(
        draw, title, (72, 300, W - 72, 950), max_size=96, min_size=56,
        color=(255, 255, 255, 255), bold=True, weight="black",
    )
    common.draw_fitted(
        draw, subtitle, (72, 1000, W - 72, 1120), max_size=44, min_size=32,
        color=common.with_alpha(accent, 255), bold=True,
    )
    common.rounded_pill(
        base, (270, 1180, 810, 1280),
        fill=common.with_alpha(accent, 255),
        text=f'COMMENT "{keyword}"',
        text_color=(15, 23, 42, 255),
    )
    return base


def _brand_chip(draw: ImageDraw.ImageDraw, palette: tuple, y: int = 84) -> None:
    accent = common.hex_to_rgb(palette[2])
    draw.rounded_rectangle((72, y, 76, y + 56), radius=2, fill=common.with_alpha(accent, 255))
    f = common.font(34, bold=True)
    draw.text((96, y + 8), config.BRAND_NAME.upper(), font=f, fill=(255, 255, 255, 235))


def _item_slide(item: dict, index: int, total: int, palette: tuple) -> Image.Image:
    W, H = 1080, 1350
    top, bottom, accent_hex, _ = palette
    accent = common.hex_to_rgb(accent_hex)
    base = common.vivid(common.vertical_gradient((W, H), top, bottom)).convert("RGBA")
    draw = ImageDraw.Draw(base, "RGBA")

    ghost = common.font(300, bold=True, weight="black")
    num = f"{index:02d}"
    gw = ghost.getlength(num)
    draw.text((W - gw - 60, -70), num, font=ghost, fill=common.with_alpha(accent, 48))

    common.draw_fitted(
        draw, item["name"], (72, 420, W - 72, 700), max_size=96, min_size=60,
        color=(255, 255, 255, 255), bold=True, weight="black",
    )
    common.draw_fitted(
        draw, item["desc"], (72, 760, W - 72, 1050), max_size=52, min_size=36,
        color=(255, 255, 255, 235), bold=True,
    )
    common.progress_dots(draw, total, index, W // 2, 1240, common.with_alpha(accent, 255), (255, 255, 255, 70))
    return base


def _cta_slide(keyword: str, page_hint: str, palette: tuple, total: int) -> Image.Image:
    W, H = 1080, 1350
    top, bottom, accent_hex, _ = palette
    accent = common.hex_to_rgb(accent_hex)
    base = common.vivid(common.vertical_gradient((W, H), top, bottom)).convert("RGBA")
    draw = ImageDraw.Draw(base, "RGBA")

    common.draw_fitted(
        draw, f'Comment "{keyword}"', (72, 300, W - 72, 560), max_size=92, min_size=60,
        color=(255, 255, 255, 255), bold=True, weight="black",
    )
    common.draw_fitted(
        draw, "and I'll send you the full list with links", (72, 600, W - 72, 760),
        max_size=52, min_size=36, color=(255, 255, 255, 240), bold=True,
    )
    common.rounded_pill(
        base, (200, 880, 880, 980),
        fill=common.with_alpha(accent, 255),
        text="FOLLOW + COMMENT = LINK IN DM",
        text_color=(15, 23, 42, 255),
    )
    f = common.font(36, bold=True)
    draw.text((72, 1120), f"impatient? {page_hint}", font=f, fill=common.with_alpha(accent, 230))
    common.progress_dots(draw, total, total - 1, W // 2, 1240, common.with_alpha(accent, 255), (255, 255, 255, 70))
    return base


def build_lead_carousel(list_id: str, for_seed: int | None = None) -> tuple[Path, list[Path]]:
    """Render a lead-magnet carousel. Returns (out_dir, [slide paths])."""
    data = load_lists()
    spec = data[list_id]
    keyword = spec["keyword"]
    rng = random.Random(for_seed if for_seed is not None else config.now_local().toordinal())
    palette = config.PALETTES[rng.randrange(len(config.PALETTES))]

    # On-slide items: cap at 5 to keep swipe depth sane; full list in DM/bio page
    shown = spec["items"][:5]
    total = len(shown) + 2

    out_dir = config.MEDIA_DIR / "leads" / f"{config.now_local():%Y-%m-%d}_{list_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    from media import stock  # optional: real photos when PEXELS_API_KEY set
    hint = (spec.get("keyword") or "").strip().lower()
    bg = stock.list_background(hint) if hint else None

    slides = [_hook_slide(spec["title"], spec["subtitle"], keyword, palette, rng, bg_img=bg)]
    for i, item in enumerate(shown, start=1):
        slides.append(_item_slide(item, i, total, palette))
    slides.append(_cta_slide(keyword, "link in bio -> Lists", palette, total))

    paths = []
    for i, s in enumerate(slides, start=1):
        p = out_dir / f"lead_{i:02d}.jpg"
        s.convert("RGB").save(p, "JPEG", quality=90)
        paths.append(p)

    # caption + auto first comment — value first, then a soft bridge to revenue
    from core import planner as _pl
    products = _pl.load_products()
    pick = products[hash(list_id) % len(products)]
    pick_benefit = ((pick.get("benefits") or "").split("|")[0] or "saves hours").strip()
    pick_trial = (pick.get("trial") or "free to start").strip()

    caption = (
        f"{spec['title']}\n\n"
        + "\n".join(f"• {i['name']} - {i['desc']}" for i in spec["items"][:3])
        + "\n... and the rest of the list\n\n"
        + f"COMMENT \"{keyword}\" and I'll send the complete list with links\n"
        + "(impatient? link in bio -> Lists)\n\n"
        + f"Bonus: the paid tool I actually pay for right now — {pick['name']}\n"
        + f"{pick_benefit}. {pick_trial}. Check it in bio if curious.\n\n"
        + "Follow " + config.BRAND_HANDLE + " — free tools weekly, paid tools only when they earn it.\n\n"
        + "Affiliate disclosure: links to the bonus pick support the page at no extra cost to you."
    )
    (out_dir / "caption.txt").write_text(caption, encoding="utf-8")
    (out_dir / "first_comment.txt").write_text(
        f'Commenting "{keyword}" does work - the list lands in your DMs.\n'
        f"Impatient? The full list with live links is in the bio under {list_id.replace('_', '-')}.",
        encoding="utf-8",
    )
    return out_dir, paths
