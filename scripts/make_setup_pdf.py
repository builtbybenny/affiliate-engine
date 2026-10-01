#!/usr/bin/env python3
"""Render docs_content/SETUP_GUIDE.md into SETUP_GUIDE.pdf (fpdf2, core fonts)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fpdf import FPDF  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "docs_content" / "SETUP_GUIDE.md"
OUT = ROOT / "SETUP_GUIDE.pdf"

ACCENT = (56, 189, 248)
DARK = (30, 41, 59)
GREY = (100, 116, 139)


class Guide(FPDF):
    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("helvetica", "", 8)
        self.set_text_color(*GREY)
        self.cell(0, 6, "Stack & Save - Setup Guide", align="L")
        self.cell(0, 6, f"Page {self.page_no()}", align="R", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(226, 232, 240)
        self.line(15, 18, 195, 18)
        self.ln(4)

    def footer(self) -> None:
        pass


def clean(text: str) -> str:
    """ASCII-safe for core fonts."""
    text = (
        text.replace("—", " - ").replace("→", "->").replace("·", "-")
        .replace("│", "|").replace("|", "|").replace("\u00a0", " ")
        .replace("✅", "[x]").replace("₹", "Rs.").replace("↓", "(below)")
    )
    # never crash on any other exotic character: swap to closest ASCII
    return text.encode("latin-1", "replace").decode("latin-1")


def main() -> None:
    md = SRC.read_text(encoding="utf-8")
    pdf = Guide(format="A4")
    pdf.set_margins(15, 15, 15)
    pdf.set_auto_page_break(True, 18)
    pdf.add_page()

    for raw in md.splitlines():
        line = raw.rstrip()
        if not line.strip():
            pdf.ln(2)
            continue
        if line.strip() == "---":
            pdf.ln(1)
            pdf.set_draw_color(226, 232, 240)
            pdf.line(15, pdf.get_y(), 195, pdf.get_y())
            pdf.ln(3)
            continue

        if line.startswith("# "):
            pdf.set_font("helvetica", "B", 17)
            pdf.set_text_color(*DARK)
            pdf.multi_cell(0, 9, clean(line[2:]), new_x="LMARGIN", new_y="NEXT")
            pdf.set_draw_color(*ACCENT)
            pdf.set_line_width(0.6)
            pdf.line(15, pdf.get_y() + 1, 90, pdf.get_y() + 1)
            pdf.ln(4)
            continue
        if line.startswith("## "):
            pdf.ln(2)
            pdf.set_font("helvetica", "B", 13)
            pdf.set_text_color(*DARK)
            pdf.multi_cell(0, 7, clean(line[3:]), new_x="LMARGIN", new_y="NEXT")
            pdf.ln(1)
            continue

        # table rows (cells WRAP long text instead of clipping)
        if line.startswith("|"):
            cells = [c.strip() for c in line.strip("|").split("|")]
            if all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                continue  # separator row
            pdf.set_font("helvetica", "", 9)
            pdf.set_text_color(*DARK)
            pdf.set_draw_color(203, 213, 225)
            pdf.set_fill_color(241, 245, 249)
            w = 180 / len(cells)
            texts = [" " + clean(c) for c in cells]

            def _cell_h(t: str) -> float:
                # real wrapped height when fpdf2 supports dry-run, else estimate
                try:
                    return pdf.multi_cell(w, 5, t, border=1, dry_run=True, output="HEIGHT")
                except Exception:
                    return 5 * max(1, int(len(t) / max(10.0, w / 1.9)) + 1)

            row_h = max(_cell_h(t) for t in texts)
            start_page, y0 = pdf.page_no(), pdf.get_y()
            for i, t in enumerate(texts):
                pdf.set_xy(15 + i * w, y0)
                pdf.multi_cell(w, 5, t, border=1, fill=(i == 0))
            if pdf.page_no() == start_page:  # row didn't span a page break
                pdf.set_y(max(y0 + row_h, pdf.get_y()))
            continue

        # code / command lines (4-space indent or inline `x`)
        if line.startswith("    "):
            pdf.set_font("courier", "", 9)
            pdf.set_text_color(15, 23, 42)
            pdf.set_fill_color(248, 250, 252)
            pdf.multi_cell(0, 5, "  " + clean(line.strip()), fill=True, new_x="LMARGIN", new_y="NEXT")
            continue

        # numbered / bullet
        m = re.match(r"^(\s*)(\d+\.\s+|-\s+|•\s+)(.*)$", line)
        if m:
            indent, bullet, body = m.groups()
            pdf.set_text_color(*DARK)
            pdf.set_font("helvetica", "", 10)
            x = pdf.get_x() + len(indent) * 1.2
            pdf.set_x(x)
            pdf.multi_cell(0, 5.2, clean(bullet + body), new_x="LMARGIN", new_y="NEXT")
            continue

        # bold start line (**Total time:** etc)
        if line.startswith("**"):
            pdf.set_font("helvetica", "B", 10)
            pdf.set_text_color(*DARK)
            pdf.multi_cell(0, 5.2, clean(line.replace("**", "")), new_x="LMARGIN", new_y="NEXT")
            continue

        pdf.set_font("helvetica", "", 10)
        pdf.set_text_color(*DARK)
        pdf.multi_cell(0, 5.2, clean(line), new_x="LMARGIN", new_y="NEXT")

    pdf.output(str(OUT))
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB, {pdf.page_no()} pages)")


if __name__ == "__main__":
    main()
