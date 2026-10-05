"""Carousel factory: renders 1080x1350 JPEG slides from product data + product images.

Slide structure:
  1. Hook slide (big title + brand chip)
  2..n. Benefit/spec slides with progress dots
  last. CTA slide (price + "Link in bio" pill)

If the product has images (data/product_images/<id>.(jpg|png|webp)), slide 1
uses the image as background under a dark scrim. Otherwise, when
PEXELS_API_KEY is set, a relevant license-free stock photo is fetched (and
cached forever in data/stock/). If neither exists, a gradient is used.
"""
from __future__ import annotations

import random
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from core import config, copywriter, planner
from media import common


def _product_image(product: dict) -> Image.Image | None:
    pid = planner.slugify(product.get("id") or product["name"])
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = config.PRODUCT_IMAGES_DIR / f"{pid}.{ext}"
        if p.exists():
            return Image.open(p).convert("RGB")
    any_img = sorted(config.PRODUCT_IMAGES_DIR.glob("*"))
    if any_img and product.get("image"):
        named = config.PRODUCT_IMAGES_DIR / product["image"]
        if named.exists():
            return Image.open(named).convert("RGB")
    return None


def _scrim(img: Image.Image, strength: int = 200) -> Image.Image:
    overlay = Image.new("RGBA", img.size, (0, 0, 0, strength))
    return Image.alpha_composite(img.convert("RGBA"), overlay)


def _soft_accent_blobs(base: Image.Image, accent: tuple[int, int, int, int]) -> None:
    w, h = base.size
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((w * 0.55, -h * 0.12, w * 1.35, h * 0.30), fill=common.with_alpha(accent[:3], 34))
    d.ellipse((-w * 0.30, h * 0.78, w * 0.35, h * 1.15), fill=common.with_alpha(accent[:3], 26))
    layer = layer.filter(ImageFilter.GaussianBlur(60))
    base.alpha_composite(layer)


def _brand_chip(draw: ImageDraw.ImageDraw, palette: tuple, y: int = 84) -> None:
    accent = common.hex_to_rgb(palette[2])
    draw.rounded_rectangle((72, y, 76, y + 56), radius=2, fill=common.with_alpha(accent, 255))
    f = common.font(34, bold=True)
    draw.text((96, y + 8), config.BRAND_NAME.upper(), font=f, fill=(255, 255, 255, 235))


def _hook_slide(product: dict, hook: str, palette: tuple, bg_img: Image.Image | None) -> Image.Image:
    W, H = 1080, 1350
    top, bottom, accent_hex, text = palette
    accent = common.hex_to_rgb(accent_hex)
    base = (
        common.vivid(common.cover_crop(bg_img, W, H)).convert("RGBA")
        if bg_img
        else common.vivid(common.vertical_gradient((W, H), top, bottom)).convert("RGBA")
    )
    if bg_img:
        base = _scrim(base, 110)
    else:
        _soft_accent_blobs(base, accent)
    draw = ImageDraw.Draw(base, "RGBA")
    _brand_chip(draw, palette)
    common.draw_fitted(
        draw, hook, (72, 260, W - 72, 900), max_size=104, min_size=56,
        color=(255, 255, 255, 255), bold=True, weight="black",
    )
    f = common.font(44, bold=True)
    name = product["name"]
    draw.text((72, 1130), name[:38], font=f, fill=common.with_alpha(accent, 255))
    return base


def _content_slide(
    body: str, index: int, total: int, palette: tuple, kicker: str
) -> Image.Image:
    W, H = 1080, 1350
    top, bottom, accent_hex, text = palette
    accent = common.hex_to_rgb(accent_hex)
    base = common.vivid(common.vertical_gradient((W, H), top, bottom)).convert("RGBA")
    _soft_accent_blobs(base, accent)
    draw = ImageDraw.Draw(base, "RGBA")

    ghost = common.font(300, bold=True)
    num = f"{index:02d}"
    gw = ghost.getlength(num)
    draw.text((W - gw - 60, -70), num, font=ghost, fill=common.with_alpha(accent, 48))

    f = common.font(34, bold=True)
    draw.text((72, 100), kicker.upper(), font=f, fill=common.with_alpha(accent, 220))

    common.draw_fitted(
        draw, body, (72, 380, W - 72, 1040), max_size=84, min_size=48,
        color=(255, 255, 255, 252), bold=True,
    )
    common.progress_dots(draw, total, index, W // 2, 1240, common.with_alpha(accent, 255), (255, 255, 255, 70))
    return base


def _cta_slide(product: dict, palette: tuple, slide_count: int) -> Image.Image:
    W, H = 1080, 1350
    top, bottom, accent_hex, text = palette
    accent = common.hex_to_rgb(accent_hex)
    base = common.vivid(common.vertical_gradient((W, H), top, bottom)).convert("RGBA")
    _soft_accent_blobs(base, accent)
    draw = ImageDraw.Draw(base, "RGBA")

    common.draw_fitted(
        draw, "Try it free today", (72, 240, W - 72, 520), max_size=96, min_size=60,
        color=(255, 255, 255, 255), bold=True,
    )
    name_f = common.font(52, bold=True)
    draw.text((72, 600), product["name"][:40], font=name_f, fill=common.with_alpha(accent, 255))

    trial = (product.get("trial") or "").strip()
    if trial:
        common.draw_fitted(
            draw, trial, (72, 700, W - 72, 800),
            max_size=56, min_size=40, color=(255, 255, 255, 235), bold=True,
        )

    common.rounded_pill(
        base, (200, 980, 880, 1090),
        fill=common.with_alpha(accent, 255),
        text="START FREE — LINK IN BIO",
        text_color=(15, 23, 42, 255),
    )
    f = common.font(34, bold=False)
    draw.text(
        (72, 1240), f"{config.BRAND_HANDLE}  |  swipe back to review",
        font=f, fill=(255, 255, 255, 200),
    )
    common.progress_dots(draw, slide_count, slide_count - 1, W // 2, 1180, common.with_alpha(accent, 255), (255, 255, 255, 70))
    return base


def build_carousel(
    product: dict,
    theme: str,
    out_dir: Path | None = None,
    for_date: date | None = None,
    seed: int | None = None,
    copy_override: dict | None = None,
    hook_override: str = "",
) -> tuple[list[Path], list[str]]:
    """Render slides; returns (file_paths, slide_texts).

    copy_override: optional {'hook': str, 'slides': [str]} from the AI
    copywriter; falls back to templates when absent.
    """
    for_date = for_date or config.now_local().date()
    rng = random.Random(seed if seed is not None else for_date.toordinal())
    palette = config.PALETTES[for_date.toordinal() % len(config.PALETTES)]

    slide_texts = copywriter.build_slide_texts(product, theme, rng)
    if copy_override:
        slide_texts = (
            [copy_override["hook"]]
            + copy_override["slides"]
            + [slide_texts[-1]]  # keep the trial/CTA end slide
        )
    if hook_override:
        slide_texts[0] = hook_override
    hook = slide_texts[0]
    bodies = slide_texts[1:-1] or ["Check the details in the caption"]
    total = len(bodies) + 2  # hook + bodies + CTA

    out_dir = out_dir or (config.CAROUSELS_DIR / planner.next_filename_slug(for_date, "carousel", product))
    out_dir.mkdir(parents=True, exist_ok=True)

    bg = _product_image(product)
    if bg is None:
        from media import stock  # optional: multi-provider stock when keys set
        bg = stock.product_background(product, portrait=True, salt=for_date.isoformat())
    slides: list[Image.Image] = [_hook_slide(product, hook, palette, bg)]
    for i, body in enumerate(bodies, start=1):
        slides.append(_content_slide(body, i, total, palette, kicker=product["name"]))
    slides.append(_cta_slide(product, palette, total))

    files: list[Path] = []
    for i, slide in enumerate(slides, start=1):
        path = out_dir / f"slide_{i:02d}.jpg"
        slide.convert("RGB").save(path, "JPEG", quality=90)
        files.append(path)

    (out_dir / "slides.txt").write_text("\n".join(slide_texts), encoding="utf-8")
    return files, slide_texts
