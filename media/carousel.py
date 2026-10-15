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


def _luma_mean(img: Image.Image) -> float:
    px = list(img.convert("L").resize((12, 12)).getdata())
    return sum(px) / 144.0


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
        # Scrim must scale with the photo. A fixed alpha left bright stock
        # photos (gray ~200 after `vivid`) washing the white hook out to
        # near-zero contrast while dark ones stayed readable. Target a
        # uniform mid-gray backdrop (~85) so headline contrast is constant
        # regardless of which stock photo got picked.
        luma = _luma_mean(base)
        target = 85.0
        alpha = 0 if luma <= target else int(255 * (1 - target / max(luma, 1)))
        base = _scrim(base, min(200, max(40, alpha)))
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


def _soft_accent_blobs_variant(base: Image.Image, accent: tuple[int, int, int, int], index: int) -> None:
    """Fallback-gradient interior slides: same accent language, but the two
    soft blobs rotate through 3 anchor compositions per slide index so
    adjacent slides never decode as near-identical fields."""
    w, h = base.size
    anchors = (
        (((0.72, -0.05, 1.45, 0.30)), ((-0.30, 0.78, 0.38, 1.14))),
        (((-0.22, -0.05, 0.62, 0.32)), ((0.58, 0.76, 1.36, 1.16))),
        (((0.28, 0.58, 1.18, 1.06)), ((-0.32, -0.06, 0.54, 0.30))),
    )
    boxes = anchors[(index - 1) % len(anchors)]
    alphas = (34, 26)
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for b, a in zip(boxes, alphas):
        d.ellipse((b[0] * w, b[1] * h, b[2] * w, b[3] * h), fill=common.with_alpha(accent[:3], a))
    layer = layer.filter(ImageFilter.GaussianBlur(60))
    base.alpha_composite(layer)


def _content_slide(
    body: str, index: int, total: int, palette: tuple, kicker: str,
    bg_img: Image.Image | None = None,
) -> Image.Image:
    """Interior slide. The FRAME (typography scale, ghost number, kicker,
    progress dots) is identical on every inner slide on purpose — same
    template per carousel-frameworks.md — while the background layer
    differs per slide: a panning/zooming crop window over the deck photo
    (or a rotating accent-blob composition on the gradient fallback),
    with the hook slide's luma-targeted scrim so type contrast stays
    constant. Shipped decks used to differ by only 3-9/255 grayscale in
    the middle slides, which reads as the same slide twice and kills the
    swipe-through (2026-10-15 rebuild)."""
    W, H = 1080, 1350
    top, bottom, accent_hex, text = palette
    accent = common.hex_to_rgb(accent_hex)
    if bg_img is not None:
        src = bg_img
        n_interior = max(1, total - 2)
        f = 0.5 if n_interior == 1 else (index - 1) / (n_interior - 1)
        zoom = 1.16 + 0.18 * ((index % 3) / 2)  # subtle per-slide zoom variety
        src_w, src_h = src.size
        scale = max(W / src_w, H / src_h) * zoom  # cover-fit + zoom
        rs = src.resize(
            (max(1, int(src_w * scale + 0.5)), max(1, int(src_h * scale + 0.5))),
            Image.LANCZOS,
        )
        slack_x, slack_y = rs.width - W, rs.height - H
        left = int(slack_x * f)  # pan the window across the photo
        top_s = int(slack_y * (0.0 if index % 2 else 0.5))  # vertical jitter
        base = common.vivid(rs.crop((left, top_s, left + W, top_s + H))).convert("RGBA")
        luma = _luma_mean(base)
        target = 85.0
        alpha = 0 if luma <= target else int(255 * (1 - target / max(luma, 1)))
        base = _scrim(base, min(200, max(40, alpha)))
    else:
        base = common.vivid(common.vertical_gradient((W, H), top, bottom)).convert("RGBA")
        _soft_accent_blobs_variant(base, accent, index)
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
    # One idea per slide (vendored carousel-frameworks.md). A repeated line
    # ships as "the same slide twice" — beehiiv 2026-10-14 actually published
    # its hook line on BOTH slide 1 and slide 2. The renderer is the last
    # line of defense: keep each line's first occurrence, drop dupes.
    _seen: set[str] = set()
    _deduped: list[str] = []
    for _t in slide_texts:
        _k = _t.strip().lower()
        if not _k or _k in _seen:
            continue
        _seen.add(_k)
        _deduped.append(_t)
    slide_texts = _deduped
    hook = slide_texts[0]
    bodies = slide_texts[1:-1] or ["Check the details in the caption"]
    total = len(bodies) + 2  # hook + bodies + CTA

    out_dir = out_dir or (config.CAROUSELS_DIR / planner.next_filename_slug(for_date, "carousel", product))
    out_dir.mkdir(parents=True, exist_ok=True)

    bg = _product_image(product)
    bg_hook = bg
    bg_body = bg  # interior slides pan the CRISP image; see comment below
    if bg is not None and bg.size[0] / bg.size[1] > 1.3:
        # data/product_images are mostly LANDSCAPE marketing banners (1.9-2.25
        # aspect vs 0.8 target) with the product's own headline baked in
        # ('THE ONE PLACE TO BUILD…'). Cover-cropping to portrait both
        # stretches the lettering and lets the baked headline duel ours
        # (2026-10-12 beehiiv slide). Clean portraits skip this branch. Only
        # the hook slide needs the full 24-blur — it owns the big title.
        # Interiors pan the lightly-blurred source under the luma-targeted
        # scrim: distinct windows per slide (2026-10-15) AND far more visible
        # photo content per slide than a 24-blur wash carries.
        bg_hook = bg.filter(ImageFilter.GaussianBlur(24))
        bg_body = bg.filter(ImageFilter.GaussianBlur(6))
    if bg is None:
        from media import stock  # optional: multi-provider stock when keys set
        bg = stock.product_background(product, portrait=True, salt=for_date.isoformat())
        bg_hook = bg_body = bg
    slides: list[Image.Image] = [_hook_slide(product, hook, palette, bg_hook)]
    for i, body in enumerate(bodies, start=1):
        slides.append(_content_slide(body, i, total, palette, kicker=product["name"], bg_img=bg_body))
    slides.append(_cta_slide(product, palette, total))

    files: list[Path] = []
    for i, slide in enumerate(slides, start=1):
        path = out_dir / f"slide_{i:02d}.jpg"
        slide.convert("RGB").save(path, "JPEG", quality=90)
        files.append(path)

    (out_dir / "slides.txt").write_text("\n".join(slide_texts), encoding="utf-8")
    fw = (copy_override or {}).get("framework") if copy_override else ""
    if fw:
        (out_dir / "framework.txt").write_text(str(fw), encoding="utf-8")
    return files, slide_texts
