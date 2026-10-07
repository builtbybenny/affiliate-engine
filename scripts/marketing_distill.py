#!/usr/bin/env python3
"""Distill + govern the vendored marketing skills (see skills/marketing/VENDORED.md).

    python scripts/marketing_distill.py --refresh   # re-clone pinned repo, sync subset,
                                                    # rebuild INDEX.md + data/marketing_quickref.md
    python scripts/marketing_distill.py --check     # verify subset integrity + quickref fresh

--refresh shallow-clones https://github.com/coreyhaines31/marketingskills at the SHA
pinned in skills/marketing/.source_sha (a branch name is not a pin), re-copies the
vetted subset, rebuilds the full-catalog INDEX.md and the quickref distillate, and
prints any drift it saw. It NEVER touches skills/marketing/QUALITY_BAR.md — that
file is hand-curated and gets a manual re-review after every refresh.

Extraction is mechanical (fixed heading names); if the vendor renames a heading the
run FAILS LOUDLY instead of silently emitting a thinner quickref.
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from core.boot import setup_console  # noqa: E402

setup_console()

SOURCE_URL = "https://github.com/coreyhaines31/marketingskills.git"
MARKETING_DIR = Path(__file__).resolve().parent.parent / "skills" / "marketing"
SHA_FILE = MARKETING_DIR / ".source_sha"
QUICKREF = Path(__file__).resolve().parent.parent / "data" / "marketing_quickref.md"
INDEX = MARKETING_DIR / "INDEX.md"

# Subset actually vendored (SKILL.md always, plus vetted reference files).
SUBSET: dict[str, list[str]] = {
    "copywriting": ["references/ai-tells.md", "references/copy-frameworks.md",
                    "references/natural-transitions.md"],
    "social": ["references/platform-limits.md", "references/platforms.md",
               "references/post-templates.md", "references/short-form-video.md"],
    "offers": ["references/offer-anatomy.md", "references/saas-offers.md"],
    "lead-magnets": ["references/format-guide.md"],
}

# (file, heading regex) -> quickref section title. Heading regexes are the
# vendor's own headings; a missing one aborts the refresh (drift = loud).
EXTRACT: list[tuple[str, str, str]] = [
    ("copywriting/SKILL.md", r"^## Copywriting Principles", "Copywriting principles"),
    ("copywriting/references/ai-tells.md", r"^## Structural Patterns",
     "AI tells — structural bans (worst offenders)"),
    ("copywriting/references/ai-tells.md", r"^## Rewrite Rules", "AI tells — rewrite rules"),
    ("copywriting/references/ai-tells.md", r"^## The Self-Check", "AI tells — self-check"),
    ("social/SKILL.md", r"^## Hook Formulas", "Hook formulas"),
    ("social/SKILL.md", r"^## Content Pillars Framework", "Content pillars"),
    ("social/references/short-form-video.md", r"^## Video Hook Library",
     "Short-form video hook library"),
    ("offers/SKILL.md", r"^## The Value Equation", "Offer value equation"),
    ("offers/SKILL.md", r"^## Banned Vocabulary", "Offer banned vocabulary"),
    ("lead-magnets/SKILL.md", r"^## Lead Magnet Principles", "Lead magnet principles"),
]

OUR_ADDITIONS_HEADING = "## OUR ADDITIONS (hand-written, survives refresh)"


def _section(text: str, heading_re: str) -> str:
    """Return the body between the matched heading and the next same-or-higher
    heading or a thematic break, whichever comes first."""
    pat = re.compile(heading_re, re.MULTILINE)
    m = pat.search(text)
    if not m:
        raise SystemExit(f"DRIFT: heading not found: {heading_re!r} — vendor text "
                         f"changed; update EXTRACT in scripts/marketing_distill.py")
    rest = text[m.end():]
    nxt = re.search(r"^#{1,2} ", rest, re.MULTILINE)  # next ## or # heading
    nxt_brk = re.search(r"^---\s*$", rest, re.MULTILINE)
    ends = [e.start() for e in (nxt, nxt_brk) if e]
    end = (min(ends) if ends else len(rest))
    return rest[:end].strip()  # body only — the caller supplies its own title


def _our_additions(old_text: str) -> str:
    if not old_text or OUR_ADDITIONS_HEADING not in old_text:
        return (f"{OUR_ADDITIONS_HEADING}\n\n"
                "(none yet — engine-specific rules discovered while running live "
                "posts get added here and survive every refresh)\n")
    return old_text[old_text.index(OUR_ADDITIONS_HEADING):].strip()


def refresh() -> None:
    sha = SHA_FILE.read_text(encoding="utf-8").strip()
    tmp = Path(tempfile.mkdtemp(prefix="msk_"))
    try:
        subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", SOURCE_URL,
                        str(tmp)], check=True)
        head = subprocess.run(["git", "-C", str(tmp), "rev-parse", "HEAD"],
                              capture_output=True, text=True, check=True).stdout.strip()
        if head != sha:
            print(f"DRIFT: pinned {sha[:12]} -> upstream now {head[:12]}; subset "
                  f"re-synced at the PINNED sha; re-pin deliberately if you want newer.")
        # sync subset at the pinned SHA
        for skill, refs in SUBSET.items():
            src = tmp / "skills" / skill
            dst = MARKETING_DIR / skill
            if dst.exists():
                shutil.rmtree(dst)
            dst.mkdir(parents=True)
            shutil.copy2(src / "SKILL.md", dst / "SKILL.md")
            (dst / "references").mkdir()
            for r in refs:
                shutil.copy2(src / r, dst / r)
        # full-catalog index (title + first sentence of description)
        catalog = sorted((tmp / "skills").iterdir())
        lines = ["# marketingskills full catalog (menu, not a meal)",
                 "",
                 f"Source: {SOURCE_URL} · enumerated at vendored refresh "
                 f"({sha[:12]}). Pull a skill into SUBSET in "
                 "scripts/marketing_distill.py when a trigger below fires.",
                 ""]
        for d in catalog:
            sk = d / "SKILL.md"
            if not sk.exists():
                continue
            text = sk.read_text(encoding="utf-8")
            desc = re.search(r"^description:\s*\"?(.+?)(\.\s|\n)", text, re.MULTILINE | re.DOTALL)
            one = re.sub(r"\s+", " ", desc.group(1)).strip() if desc else ""
            mark = " ← vendored" if d.name in SUBSET else ""
            lines.append(f"- **{d.name}**{mark} — {one[:180]}")
        trigger = ["", "## Pull triggers (staged adoption)",
                   "- Newsletter/email list exists → `emails`",
                   "- Any paid promotion budget → `ad-creative`, `ads`",
                   "- Bio/link page traffic worth optimizing → `cro`, `pricing`",
                   "- Website/blog surface appears → `seo-audit`, `site-architecture`, `schema`",
                   "- Churn/backlash signals in comments → `customer-research`",
                   "- A/B evidence volume (≥20 posts/metric) → `ab-testing`, `analytics`"]
        lines += trigger
        INDEX.write_text("\n".join(lines) + "\n", encoding="utf-8")
        # quickref
        old = QUICKREF.read_text(encoding="utf-8") if QUICKREF.exists() else ""
        parts = ["# Marketing quickref (distilled from vendored skills — human reference)",
                 "",
                 f"Distilled from skills/marketing/* pinned at {sha[:12]}. "
                 "Regenerate: python scripts/marketing_distill.py --refresh",
                 ""]
        for fname, heading, title in EXTRACT:
            body = _section((MARKETING_DIR / fname).read_text(encoding="utf-8"), heading)
            parts += [f"## {title}", "", f"_(from {fname})_", "", body, ""]
        parts += [_our_additions(old)]
        QUICKREF.write_text("\n".join(parts), encoding="utf-8")
        print(f"quickref: {QUICKREF} ({len(QUICKREF.read_text(encoding='utf-8').splitlines())} lines)")
        print(f"index: {INDEX} ({len(catalog)} skills)")
        print("QUALITY_BAR.md untouched — re-review it by hand against drift above.")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check() -> int:
    missing = []
    for skill, refs in SUBSET.items():
        if not (MARKETING_DIR / skill / "SKILL.md").exists():
            missing.append(str(skill / "SKILL.md"))
        for r in refs:
            if not (MARKETING_DIR / skill / r).exists():
                missing.append(str(skill / r))
    for f in (QUALITY := MARKETING_DIR / "QUALITY_BAR.md", INDEX, QUICKREF):
        if not f.exists():
            missing.append(str(f))
    if missing:
        print("MISSING:", ", ".join(missing))
        return 1
    print("subset + QUALITY_BAR + INDEX + quickref all present")
    return 0


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    if args.refresh:
        refresh()
    check()


if __name__ == "__main__":
    main()
