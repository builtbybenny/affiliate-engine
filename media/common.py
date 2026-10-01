"""Shared drawing helpers: fonts, gradients, fitted text, progress dots."""
from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from core import config

_SYSTEM_FONT_CANDIDATES = [
    # Windows
    r"C:\Windows\Fonts\arialbd.ttf",
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeuib.ttf",
    # macOS
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    # Linux
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

_font_cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

# Weight mapping: which file in assets/fonts serves each role.
# Drop-in names that unlock all three: Inter-Bold.ttf, Inter-Regular.ttf,
# Inter-Black.ttf (or Montserrat-Bold / Montserrat-Regular / Montserrat-Black).
_WEIGHT_FILES = {
    "black": ("Inter-Black", "Montserrat-Black", "Archivo-Black", "Poppins-Black"),
    "bold": ("Inter-Bold", "Montserrat-Bold", "Archivo-Bold", "Poppins-Bold"),
    "regular": ("Inter-Regular", "Montserrat-Regular", "Archivo-Regular", "Poppins-Regular"),
}


def _pick_from_dir(names: tuple[str, ...]) -> str:
    if not config.FONTS_DIR.exists():
        return ""
    files = {p.stem.lower(): p for p in config.FONTS_DIR.glob("*") if p.suffix.lower() in (".ttf", ".otf")}
    for name in names:
        if name.lower() in files:
            return str(files[name.lower()])
    # loose match: first font containing the family fragment
    for name in names:
        frag = name.split("-")[0].lower()
        for stem, p in files.items():
            if frag in stem:
                return str(p)
    return ""


def find_font(bold: bool = True, weight: str = "") -> str:
    """User fonts in assets/fonts win. weight: 'black'|'bold'|'regular'."""
    if weight:
        hit = _pick_from_dir(_WEIGHT_FILES.get(weight, ()))
        if hit:
            return hit
    if config.FONTS_DIR.exists():
        candidates = sorted(config.FONTS_DIR.glob("*.ttf")) + sorted(config.FONTS_DIR.glob("*.typ"))
        bolds = [c for c in candidates if "black" in c.name.lower() or "bold" in c.name.lower()]
        if bold and bolds:
            return str(bolds[0])
        if candidates:
            return str(candidates[0])
    for p in _SYSTEM_FONT_CANDIDATES:
        if Path(p).exists():
            if bold and "bold" not in p.lower() and p.endswith(".ttc"):
                continue
            return p
    return ""


def font(size: int, bold: bool = True, weight: str = "") -> ImageFont.FreeTypeFont:
    key = (f"{weight or ('bold' if bold else 'regular')}-{size}", size)
    if key not in _font_cache:
        path = find_font(bold, weight)
        _font_cache[key] = (
            ImageFont.truetype(path, size) if path else ImageFont.load_default()
        )
    return _font_cache[key]


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    h = h.lstrip("#")
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))  # type: ignore[return-value]


def with_alpha(rgb: tuple[int, int, int], alpha: int) -> tuple[int, int, int, int]:
    return (rgb[0], rgb[1], rgb[2], alpha)


def vertical_gradient(size: tuple[int, int], top: str, bottom: str) -> Image.Image:
    w, h = size
    c1, c2 = hex_to_rgb(top), hex_to_rgb(bottom)
    strip = Image.new("RGB", (1, h))
    px = strip.load()
    assert px is not None
    for y in range(h):
        t = y / max(1, h - 1)
        px[0, y] = (
            int(c1[0] + (c2[0] - c1[0]) * t),
            int(c1[1] + (c2[1] - c1[1]) * t),
            int(c1[2] + (c2[2] - c1[2]) * t),
        )
    return strip.resize((w, h))


def wrap_text(text: str, f: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words, current = para.split(), ""
        for word in words:
            trial = f"{current} {word}".strip()
            if f.getlength(trial) <= max_width or not current:
                current = trial
            else:
                lines.append(current)
                current = word
        lines.append(current)
    return lines


def draw_fitted(
    draw: ImageDraw.ImageDraw,
    text: str,
    box: tuple[int, int, int, int],
    max_size: int,
    min_size: int,
    color: tuple[int, int, int, int],
    bold: bool = True,
    align: str = "left",
    weight: str = "",
) -> int:
    """Draw text wrapped inside box (x0,y0,x1,y1), shrinking until it fits. Returns bottom y."""
    x0, y0, x1, y1 = box
    max_w, max_h = x1 - x0, y1 - y0
    size = max_size
    while size >= min_size:
        f = font(size, bold, weight)
        lines = wrap_text(text, f, max_w)
        line_h = int(size * 1.22)
        if len(lines) * line_h <= max_h and all(
            f.getlength(ln) <= max_w for ln in lines
        ):
            y = y0
            for ln in lines:
                w = f.getlength(ln)
                x = x0 if align == "left" else int(x0 + (max_w - w) / 2)
                draw.text((x, y), ln, font=f, fill=color)
                y += line_h
            return y
        size -= 4
    return y0


def rounded_pill(
    img: Image.Image,
    box: tuple[int, int, int, int],
    fill: tuple[int, int, int, int],
    text: str,
    text_color: tuple[int, int, int, int],
) -> None:
    """Pill button that auto-shrinks its label to fit inside the shape."""
    draw = ImageDraw.Draw(img, "RGBA")
    draw.rounded_rectangle(box, radius=(box[3] - box[1]) // 2, fill=fill)
    max_w = (box[2] - box[0]) - 56  # side padding
    size = 46
    while size > 18 and font(size, bold=True).getlength(text) > max_w:
        size -= 2
    f = font(size, bold=True)
    w = f.getlength(text)
    x = (box[0] + box[2]) / 2 - w / 2
    y = (box[1] + box[3]) / 2 - size * 0.62
    draw.text((x, y), text, font=f, fill=text_color)


def progress_dots(
    draw: ImageDraw.ImageDraw,
    total: int,
    current: int,
    center_x: int,
    y: int,
    accent: tuple[int, int, int, int],
    dim: tuple[int, int, int, int],
) -> None:
    if total <= 1:
        return
    gap, r = 44, 7
    total_w = (total - 1) * gap
    x = center_x - total_w / 2
    for i in range(total):
        color = accent if i == current else dim
        draw.ellipse((x - r, y - r, x + r, y + r), fill=color)
        x += gap


def cover_crop(img: Image.Image, width: int, height: int) -> Image.Image:
    """Scale + crop image to exactly width x height (object-fit: cover)."""
    src_w, src_h = img.size
    scale = max(width / src_w, height / src_h)
    new_size = (int(src_w * scale + 0.5), int(src_h * scale + 0.5))
    img = img.resize(new_size, Image.LANCZOS)
    left = (img.width - width) // 2
    top = (img.height - height) // 2
    return img.crop((left, top, left + width, top + height))
