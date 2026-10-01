#!/usr/bin/env python3
"""Builds public/preview.html with all media embedded as base64 (no server needed)."""
from __future__ import annotations

import base64
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PUBLIC = Path(__file__).resolve().parent.parent / "public"


def latest_carousel() -> Path:
    dirs = sorted(
        (PUBLIC / "media" / "carousels").glob("*"),
        key=lambda p: p.stat().st_mtime,
    )
    if not dirs:
        raise SystemExit("No carousels found — run scripts/generate.py first.")
    return dirs[-1]


def latest_reel() -> Path:
    files = sorted(
        (PUBLIC / "media" / "reels").glob("*.mp4"),
        key=lambda p: p.stat().st_mtime,
    )
    if not files:
        raise SystemExit("No reels found — run scripts/generate.py first.")
    return files[-1]


def b64(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode()


def reel_frames(mp4: Path, n: int = 6) -> list[str]:
    frames = []
    with tempfile.TemporaryDirectory() as td:
        subprocess.run(
            ["ffmpeg", "-y", "-i", str(mp4), "-vf", f"fps=1/{15/n}", "-frames:v", str(n), f"{td}/f%02d.jpg"],
            check=True, capture_output=True,
        )
        for f in sorted(Path(td).glob("f*.jpg"))[:n]:
            frames.append(b64(f))
    return frames


def latest_leads() -> list[Path]:
    lead_dirs = sorted(
        (PUBLIC / "media" / "leads").glob("*") if (PUBLIC / "media" / "leads").exists() else [],
        key=lambda p: p.stat().st_mtime,
    )
    if not lead_dirs:
        return []
    return sorted(lead_dirs[-1].glob("lead_*.jpg"))


def main() -> None:
    carousel_dir, reel_file = latest_carousel(), latest_reel()
    slides = sorted(carousel_dir.glob("slide_*.jpg"))
    imgs = "".join(
        f'<img src="data:image/jpeg;base64,{b64(s)}">' for s in slides
    )
    frames = reel_frames(reel_file)
    vid = "".join(f'<img src="data:image/jpeg;base64,{f}">' for f in frames)
    lead_imgs = latest_leads()
    lead_html = (
        "".join(f'<img src="data:image/jpeg;base64,{b64(s)}">' for s in lead_imgs)
        if lead_imgs else "<p>(no lead-magnet carousels generated yet)</p>"
    )
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>Affiliate Engine preview</title>
<style>
body{{background:#0b1020;color:#e2e8f0;font-family:system-ui,sans-serif;margin:24px}}
h2{{font-size:1rem;color:#94a3b8;margin:28px 0 10px}}
.row{{display:flex;gap:14px;flex-wrap:wrap}}
.row img{{height:340px;border-radius:12px;border:1px solid #1e293b}}
</style></head><body>
<h1>Affiliate Engine — generated output</h1>
<h2>Carousel slides (1080×1350) — swiped in order on Instagram</h2>
<div class="row">{imgs}</div>
<h2>Reel frames (1080×1920 @30fps, 15s — animated captions + Ken Burns zoom)</h2>
<div class="row">{vid}</div>
<h2>Lead-magnet carousel (comment-keyword CTA)</h2>
<div class="row">{lead_html}</div>
</body></html>"""
    (PUBLIC / "preview.html").write_text(page, encoding="utf-8")
    print(f"wrote {PUBLIC / 'preview.html'} ({(PUBLIC/'preview.html').stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
