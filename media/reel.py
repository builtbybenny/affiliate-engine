"""Reel factory: turn one product image into a 1080x1920 MP4 reel.

Three-scene structure (2026-10-04 quality pass):
  1. INTRO     - the product NAME revealed big under the hook (the app must
                 be named on screen; the hook itself is pain-led by design)
  2. BENEFITS  - one line at a time, whole-block rise+fade (no ghost-word
                 flashing), index badge, product chip pinned top-right
  3. OUTRO     - end card: product name + trial + big CTA, then a 0.5s fade
                 to black so the video never hard-cuts.
Duration adapts to line count (~2.6s/line) unless explicitly passed.
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
    # 110 was double-dimming: dark source image + heavy veil on top.
    # 60 keeps white type readable while the footage stays lit.
    overlay = Image.new("RGBA", frame.size, (0, 0, 0, 60))
    return Image.alpha_composite(frame, overlay)


def _ease(x: float) -> float:
    """Smoothstep 0..1 (soft in, soft out — no linear/robotic feel)."""
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _fit_font(text: str, max_w: int, size: int = 72) -> tuple:
    f = common.font(size, bold=True)
    while size > 20 and f.getlength(text) > max_w:
        size -= 4
        f = common.font(size, bold=True)
    return f, size


def _draw_caption(
    frame: Image.Image, text: str, t: float, duration: float,
    palette: tuple, index: int = 1, total: int = 1,
) -> None:
    """Benefit line: whole block rises+fades in, holds, fades out.

    Replaces the old per-word ghost reveal (words sat at alpha 60 until
    'spoken' — it read as flashing text, not motion design).
    """
    a_in = _ease(t / 0.45)
    a_out = _ease((duration - t) / 0.30)
    a = min(a_in, a_out)
    if a <= 0.01:
        return
    alpha = int(255 * a)
    rise = int(46 * (1 - a_in))
    accent = common.hex_to_rgb(palette[2])
    y = H - 520 + rise

    f, _ = _fit_font(text, W - 140)
    line_w = f.getlength(text)
    x = (W - line_w) / 2

    band = Image.new("RGBA", frame.size, (0, 0, 0, 0))
    bd = ImageDraw.Draw(band)
    bd.rounded_rectangle((60, y - 90, W - 60, y + 170), radius=36,
                         fill=(0, 0, 0, int(70 * a)))
    frame.alpha_composite(band)
    draw = ImageDraw.Draw(frame, "RGBA")

    # Index badge: '02 / 04' in accent — signals there's more coming.
    if total > 1:
        fb = common.font(40, bold=True)
        label = f"{index:02d} / {total:02d}"
        bw = fb.getlength(label)
        draw.text(((W - bw) / 2, y - 158), label, font=fb,
                  fill=common.with_alpha(accent, alpha))

    draw.text((x, y), text, font=f, fill=(255, 255, 255, alpha))


def _draw_chrome(
    frame: Image.Image, hook: str, brand: str, progress: float,
    palette: tuple, product_name: str = "", show_hook: bool = True,
    show_cta: bool = True,
) -> None:
    draw = ImageDraw.Draw(frame, "RGBA")
    accent = common.hex_to_rgb(palette[2])

    # Brand chip top-left
    f = common.font(40, bold=True)
    draw.rounded_rectangle((60, 150, 60 + f.getlength(brand) + 44, 226), radius=38, fill=(0, 0, 0, 120))
    draw.text((82, 168), brand, font=f, fill=(255, 255, 255, 240))

    # Product chip top-right: the app is named on EVERY frame.
    if product_name:
        label = product_name[:24]
        fp = common.font(40, bold=True)
        pw = fp.getlength(label) + 44
        px = W - 60 - pw
        draw.rounded_rectangle((px, 150, W - 60, 226), radius=38,
                               fill=common.with_alpha(accent, 235))
        draw.text((px + 22, 168), label, font=fp, fill=(15, 23, 42, 255))

    # Hook line under chip
    if show_hook and hook:
        common.draw_fitted(
            draw, hook, (60, 280, W - 60, 470), max_size=64, min_size=40,
            color=(255, 255, 255, 255), bold=True,
        )

    # Progress bar bottom
    bar_y = H - 120
    draw.rounded_rectangle((60, bar_y, W - 60, bar_y + 12), radius=6, fill=(255, 255, 255, 70))
    draw.rounded_rectangle((60, bar_y, 60 + int((W - 120) * min(1.0, progress)), bar_y + 12), radius=6, fill=common.with_alpha(accent, 255))

    # CTA pill
    if show_cta:
        common.rounded_pill(frame, (W // 2 - 320, bar_y - 210, W // 2 + 320, bar_y - 100),
                            fill=common.with_alpha(accent, 235), text="FREE TRIAL IN BIO",
                            text_color=(15, 23, 42, 255))


def _draw_intro(frame: Image.Image, product: dict, palette: tuple, t: float) -> None:
    """Scene 1: the product name revealed big (app named in the first 3s)."""
    a = _ease(t / 0.5)
    if a <= 0.01:
        return
    accent = common.hex_to_rgb(palette[2])
    rise = int(40 * (1 - a))
    draw = ImageDraw.Draw(frame, "RGBA")
    common.draw_fitted(
        draw, product["name"], (72, 1300 + rise, W - 72, 1470 + rise),
        max_size=104, min_size=56, weight="black",
        color=common.with_alpha(accent, int(255 * a)), align="center",
    )
    trial = (product.get("trial") or "").strip()
    if trial:
        ft = common.font(40, bold=False)
        tw = ft.getlength(trial)
        draw.text(((W - tw) / 2, 1490 + rise), trial, font=ft,
                  fill=(255, 255, 255, int(225 * a)))


def _draw_outro(frame: Image.Image, product: dict, palette: tuple) -> None:
    """Scene 3: end card — name, trial, big CTA. The reel lands instead of stopping."""
    frame.alpha_composite(Image.new("RGBA", frame.size, (0, 0, 0, 85)))
    accent = common.hex_to_rgb(palette[2])
    draw = ImageDraw.Draw(frame, "RGBA")
    common.draw_fitted(
        draw, product["name"], (72, 560, W - 72, 840),
        max_size=120, min_size=64, weight="black",
        color=(255, 255, 255, 255), align="center",
    )
    trial = (product.get("trial") or "").strip()
    if trial:
        common.draw_fitted(
            draw, trial, (72, 880, W - 72, 970), max_size=52, min_size=36,
            color=common.with_alpha(accent, 245), align="center",
        )
    common.rounded_pill(
        frame, (140, 1080, W - 140, 1210),
        fill=common.with_alpha(accent, 255), text="START FREE — LINK IN BIO",
        text_color=(15, 23, 42, 255),
    )
    fh = common.font(38, bold=False)
    hw = fh.getlength(config.BRAND_HANDLE)
    draw.text(((W - hw) / 2, 1290), config.BRAND_HANDLE, font=fh,
              fill=(255, 255, 255, 210))


def _fade_to_black(frame: Image.Image, t: float, duration: float) -> None:
    """Final 0.5s fade — no hard cut on the last benefit line."""
    fade = 0.5
    if t > duration - fade:
        a = int(255 * min(1.0, (t - (duration - fade)) / fade))
        frame.alpha_composite(Image.new("RGBA", frame.size, (0, 0, 0, a)))


def build_reel(
    product: dict,
    theme: str,
    out_path: Path | None = None,
    for_date: date | None = None,
    seed: int | None = None,
    duration: float | None = None,
    copy_override: dict | None = None,
    hook_override: str = "",
) -> tuple[Path, str]:
    """Render reel; returns (mp4_path, caption).

    copy_override: optional {'hook': str, 'slides': [str], 'caption': str}
    from the AI copywriter; template copy is the fallback. 'slides' become
    the on-screen benefit scenes (one line each).

    duration: None = adaptive (~2.6s per line + 2.8s intro + 3s outro,
    floor 15s). Explicit values are honored (verify scripts pass 4.0).
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
    benefits = planner.parse_benefits(product)
    # On-screen lines: AI-written slides first (they name the tool and are
    # written for the screen), CSV benefits as the fallback.
    lines = [str(s).strip() for s in (copy_override or {}).get("slides", []) if str(s).strip()]
    if not lines:
        lines = benefits or ["Check the link in bio"]
    lines = lines[:5]
    caption = (
        copy_override["caption"]
        if copy_override and copy_override.get("caption")
        else copywriter.build_caption(product, theme, for_date, rng)
    )

    if duration is None:
        duration = round(max(15.0, 2.8 + 3.0 + 2.6 * len(lines)), 1)
    intro = min(2.8, duration * 0.18)
    outro = min(3.0, duration * 0.18)
    mid = max(0.6, duration - intro - outro)
    slice_t = mid / len(lines)

    out_path = out_path or (config.REELS_DIR / f"{planner.next_filename_slug(for_date, 'reel', product)}.mp4")
    out_path.parent.mkdir(parents=True, exist_ok=True)

    total_frames = int(duration * FPS)
    bg = common.vivid(common.cover_crop(src, W, H))

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

        n_lines = len(lines)
        name = product["name"]
        vivid_cache: dict[int, Image.Image] = {}
        for i in range(total_frames):
            t = i / FPS
            if video_frames:
                j = i % len(video_frames)
                if j not in vivid_cache:
                    vf = Image.open(video_frames[j])
                    vivid_cache[j] = common.vivid(
                        common.cover_crop(vf, W, H).convert("RGB")
                    ).convert("RGBA")
                frame = vivid_cache[j]
            else:
                frame = _base_frame(bg, t / duration)
            # _scrim returns a fresh image, so the cached vivid frame is safe
            frame = _scrim(frame)
            progress = t / duration
            if t < intro:
                _draw_chrome(frame, hook, config.BRAND_HANDLE, progress,
                             palette, product_name=name)
                _draw_intro(frame, product, palette, t)
            elif t < intro + mid:
                idx = min(n_lines - 1, int((t - intro) / slice_t))
                local_t = t - intro - idx * slice_t
                _draw_chrome(frame, hook, config.BRAND_HANDLE, progress,
                             palette, product_name=name)
                _draw_caption(frame, lines[idx], local_t, slice_t, palette,
                              index=idx + 1, total=n_lines)
            else:
                _draw_outro(frame, product, palette)
                _draw_chrome(frame, hook, config.BRAND_HANDLE, progress,
                             palette, product_name=name,
                             show_hook=False, show_cta=False)
            _fade_to_black(frame, t, duration)
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
            fade_out_start = max(0.0, duration - 2.0)
            _run([
                _ffmpeg_bin(), "-y",
                "-i", str(silent), "-i", str(music),
                "-filter_complex",
                f"[1:a]atrim=0:{duration},asetpts=PTS-STARTPTS,volume=0.9,"
                f"afade=t=in:st=0:d=0.8,afade=t=out:st={fade_out_start:.1f}:d=2.0[a]",
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
