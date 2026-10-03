"""Reel factory: turn one product image into a 1080x1920 MP4 reel.

No editing skills needed: it auto-scales your still image with a slow Ken
Burns zoom, cycles animated caption lines, and adds a progress bar.
Background priority: data/product_images/<id>.jpg (your screenshot) ->
Pexels stock photo (needs PEXELS_API_KEY, cached in data/stock/) ->
branded gradient. Free stack: Pillow frames + ffmpeg (installed, free).
"""
from __future__ import annotations

import os
import random
import shutil
import subprocess
import tempfile
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw

from core import config, copywriter, planner
from media import common

W, H, FPS = 1080, 1920, 30


def _ffmpeg_bin() -> str:
    bin_path = os.getenv("FFMPEG_BIN", "ffmpeg")
    if shutil.which(bin_path) is None:
        raise SystemExit(
            "ffmpeg not found. Install it (free): "
            "Windows: winget install Gyan.FFmpeg | macOS: brew install ffmpeg | "
            "Ubuntu/Debian: sudo apt install ffmpeg  (or set FFMPEG_BIN)"
        )
    return bin_path


def _run(cmd: list[str]) -> None:
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{proc.stderr[-2000:]}")


def _base_frame(bg: Image.Image, t_norm: float) -> Image.Image:
    """Ken Burns: slow zoom from 1.0 to 1.12 over the whole video."""
    zoom = 1.0 + 0.12 * t_norm
    img_w, img_h = bg.size
    crop_w, crop_h = int(img_w / zoom), int(img_h / zoom)
    x = (img_w - crop_w) // 2
    y = (img_h - crop_h) // 2 + int(30 * t_norm)  # slight downward drift
    frame = bg.crop((x, y, x + crop_w, y + crop_h)).resize((W, H), Image.LANCZOS)
    return frame.convert("RGBA")


def _scrim(frame: Image.Image) -> Image.Image:
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 110))
    return Image.alpha_composite(frame, overlay)


def _draw_caption(frame: Image.Image, text: str, t: float, duration: float, palette: tuple) -> None:
    """Animated caption: words fade in as 'spoken' over the line duration."""
    draw = ImageDraw.Draw(frame, "RGBA")
    accent = common.hex_to_rgb(palette[2])
    words = text.split()
    fade_t = min(1.0, max(0.0, t / max(0.001, duration * 0.7)))
    shown = max(1, int(len(words) * fade_t + 0.999))

    # Fit-to-width: long benefit lines crop at the frame edges otherwise.
    # (The per-word fade can't use common.draw_fitted, so shrink instead.)
    size = 72
    f = common.font(size, bold=True)
    while size > 20 and sum(f.getlength(w) for w in words) + f.getlength(" ") * (len(words) - 1) > W - 140:
        size -= 4
        f = common.font(size, bold=True)
    space_w = f.getlength(" ")
    line_w = sum(f.getlength(w) for w in words) + space_w * (len(words) - 1)
    x = (W - line_w) / 2
    y = H - 520

    # Soft backdrop band
    band = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    bd.rounded_rectangle((60, y - 90, W - 60, y + 170), radius=36, fill=(0, 0, 0, 90))
    frame.alpha_composite(band)
    draw = ImageDraw.Draw(frame, "RGBA")

    for i, word in enumerate(words):
        wlen = f.getlength(word)
        alpha = 255 if i < shown else 60
        # bounce-in scale hint via slight y offset for the newest word
        dy = -8 if i == shown - 1 and fade_t < 1 else 0
        draw.text((x, y + dy), word, font=f, fill=(255, 255, 255, alpha))
        x += wlen + space_w


def _draw_chrome(frame: Image.Image, hook: str, brand: str, progress: float, palette: tuple) -> None:
    draw = ImageDraw.Draw(frame, "RGBA")
    accent = common.hex_to_rgb(palette[2])

    # Brand chip top-left
    f = common.font(40, bold=True)
    draw.rounded_rectangle((60, 150, 60 + f.getlength(brand) + 44, 226), radius=38, fill=(0, 0, 0, 120))
    draw.text((82, 168), brand, font=f, fill=(255, 255, 255, 240))

    # Hook line under chip
    common.draw_fitted(
        draw, hook, (60, 280, W - 60, 470), max_size=64, min_size=40,
        color=(255, 255, 255, 255), bold=True,
    )

    # Progress bar bottom
    bar_y = H - 120
    draw.rounded_rectangle((60, bar_y, W - 60, bar_y + 12), radius=6, fill=(255, 255, 255, 70))
    draw.rounded_rectangle((60, bar_y, 60 + int((W - 120) * progress), bar_y + 12), radius=6, fill=common.with_alpha(accent, 255))

    # CTA pill
    common.rounded_pill(frame, (W // 2 - 320, bar_y - 210, W // 2 + 320, bar_y - 100),
                        fill=common.with_alpha(accent, 235), text="FREE TRIAL IN BIO",
                        text_color=(15, 23, 42, 255))


def build_reel(
    product: dict,
    theme: str,
    out_path: Path | None = None,
    for_date: date | None = None,
    seed: int | None = None,
    duration: float = 15.0,
    copy_override: dict | None = None,
    hook_override: str = "",
) -> tuple[Path, str]:
    """Render reel; returns (mp4_path, caption).

    copy_override: optional {'hook': str, 'caption': str} from the AI
    copywriter; template copy is the fallback.
    """
    for_date = for_date or config.now_local().date()
    rng = random.Random(seed if seed is not None else for_date.toordinal() + 1)
    palette = config.PALETTES[(for_date.toordinal() + 1) % len(config.PALETTES)]

    # Source image (reuse product image; fall back to a branded gradient card)
    src = None
    pid = planner.slugify(product.get("id") or product["name"])
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = config.PRODUCT_IMAGES_DIR / f"{pid}.{ext}"
        if p.exists():
            src = Image.open(p).convert("RGB")
            break
    salt = for_date.isoformat()
    if src is None:
        from media import stock  # optional: multi-provider stock when keys set
        src = stock.product_background(product, portrait=True, salt=salt)
    if src is None:
        src = common.vertical_gradient((W, H), palette[0], palette[1])

    hook = (
        hook_override
        or (copy_override["hook"] if copy_override and copy_override.get("hook") else "")
        or copywriter.pick_hook(theme, product, rng)
    )
    benefits = planner.parse_benefits(product) or ["Check the link in bio"]
    caption = (
        copy_override["caption"]
        if copy_override and copy_override.get("caption")
        else copywriter.build_caption(product, theme, for_date, rng)
    )

    out_path = out_path or (config.REELS_DIR / f"{planner.next_filename_slug(for_date, 'reel', product)}.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_frames = int(duration * FPS)
    bg = common.cover_crop(src, W, H)

    with tempfile.TemporaryDirectory() as tmp:
        frames_dir = Path(tmp) / "frames"
        frames_dir.mkdir()

        # Stock footage background (multi-provider, cached, Pexels video key):
        # real motion beats a Ken Burns still — falls back on ANY failure.
        video_frames: list[Path] | None = None
        try:
            from media import stock
            vdir = Path(tmp) / "vid"
            vdir.mkdir()
            video_frames = stock.video_bg_frames(
                product, salt, total_frames, W, H, FPS, vdir,
            )
        except Exception:
            video_frames = None

        n_captions = len(benefits)
        for i in range(total_frames):
            t = i / FPS
            if video_frames:
                vf = Image.open(video_frames[i % len(video_frames)])
                frame = common.cover_crop(vf, W, H).convert("RGBA")
            else:
                frame = _base_frame(bg, t / duration)
            frame = _scrim(frame)
            # rotate through benefit lines, each shown for an equal slice
            idx = min(n_captions - 1, int(t / (duration / n_captions)))
            local_t = t - idx * (duration / n_captions)
            _draw_chrome(frame, hook, config.BRAND_HANDLE, t / duration, palette)
            _draw_caption(frame, benefits[idx], local_t, duration / n_captions, palette)
            frame.convert("RGB").save(frames_dir / f"f_{i:05d}.jpg", "JPEG", quality=88)

        # Silent video first; audio burned in below if a free track exists
        silent = Path(tmp) / "silent.mp4"
        _run([
            _ffmpeg_bin(), "-y",
            "-framerate", str(FPS), "-i", str(frames_dir / "f_%05d.jpg"),
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-preset", "medium", "-crf", "20",
            str(silent),
        ])

        music = _pick_music(rng, theme)
        recording = _pick_recording(product)
        if recording:
            _prepend_recording(silent, recording, out_path, seconds=8.0)
        elif music:
            fade_out_start = max(0.0, duration - 1.5)
            _run([
                _ffmpeg_bin(), "-y",
                "-i", str(silent), "-i", str(music),
                "-filter_complex",
                f"[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS,volume=0.9,"
                f"afade=t=in:st=0:d=0.8,afade=t=out:st={fade_out_start:.1f}:d=1.5[a]",
                "-map", "0:v", "-map", "[a]",
                "-c:v", "copy", "-c:a", "aac", "-shortest",
                str(out_path),
            ])
        else:
            shutil.move(str(silent), str(out_path))

    (out_path.parent / (out_path.stem + "_caption.txt")).write_text(caption, encoding="utf-8")
    return out_path, caption


# Mood matching: reels feel right when the bed fits the content.
# Theme -> preferred mood. Track files encode their mood in the name,
# e.g. calm-01.mp3, upbeat-01.mp3, corporate-01.mp3.
MOOD_FOR_THEME = {
    "before_after": "calm",       # transformation story, focused
    "tutorial_teaser": "calm",    # how-to, concentration
    "deal_alert": "upbeat",       # urgency, energy
    "free_tools": "upbeat",       # generosity, momentum
    "saas_stack": "corporate",    # clean, professional roundup
    "comparison": "corporate",    # sober head-to-head
    "myth_vs_fact": "corporate",  # authoritative correction
}


def _pick_music(rng, theme: str = "") -> Path | None:
    """Pick a royalty-free track from assets/music, matched to the theme.

    File naming: <mood>-<anything>.mp3 (calm-01.mp3, upbeat-01.mp3,
    corporate-01.mp3 ...). Falls back to any track in the folder when no
    mood-prefixed file exists, and to silence when the folder is empty.
    """
    all_tracks = sorted(config.MUSIC_DIR.glob("*.mp3")) + sorted(config.MUSIC_DIR.glob("*.m4a"))
    if not all_tracks:
        return None
    mood = MOOD_FOR_THEME.get(theme, "")
    if mood:
        fitting = [t for t in all_tracks if t.stem.lower().startswith(mood)]
        if fitting:
            return rng.choice(fitting)
    return rng.choice(all_tracks)  # no mood files yet -> use whatever exists


def _pick_recording(product: dict) -> Path | None:
    """Optional screen recording: data/screen_recordings/<id>.(mp4|mov|mkv|webm).

    If present, the first `seconds` of the reel show your real product UI
    (scaled/cropped to 9:16) — the single highest-converting format for SaaS.
    """
    pid = planner.slugify(product.get("id") or product["name"])
    rec_dir = config.ROOT / "data" / "screen_recordings"
    for ext in ("mp4", "mov", "mkv", "webm"):
        p = rec_dir / f"{pid}.{ext}"
        if p.exists():
            return p
    return None


def _prepend_recording(silent: Path, recording: Path, out_path: Path, seconds: float) -> None:
    """Concat: [0..s) real screen recording + [s..end) rendered motion segment."""
    _run([
        _ffmpeg_bin(), "-y",
        "-i", str(recording), "-i", str(silent),
        "-filter_complex",
        "[0:v]trim=0:" f"{seconds}",",setpts=PTS-STARTPTS,fps=30,"
        "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,setsar=1[v0];"
        "[1:v]trim=start=" f"{seconds}",",setpts=PTS-STARTPTS,fps=30,setsar=1[v1];"
        "[v0][v1]concat=n=2:v=1:a=0[outv]",
        "-map", "[outv]",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
        str(out_path),
    ])
