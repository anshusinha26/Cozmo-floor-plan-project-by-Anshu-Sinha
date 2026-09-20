#!/usr/bin/env python
"""Render Markdown to PDF without pandoc or LaTeX.

Deliberately plain: headings, paragraphs, bullets, tables, code and inline
bold. Enough to check the page count and to hand someone a readable document
on a machine with no system tools installed.

    python scripts/md_to_pdf.py in.md out.pdf
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        HRFlowable,
        ListFlowable,
        ListItem,
        Paragraph,
        Preformatted,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )
    from reportlab.lib import colors
except ImportError:  # pragma: no cover
    print("reportlab is not installed; run: uv pip install reportlab", file=sys.stderr)
    raise SystemExit(2)


def inline(text: str) -> str:
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`(.+?)`", r'<font face="Courier" size="7.5">\1</font>', text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r"\1", text)
    return text


def build(src: Path, out: Path) -> int:
    styles = getSampleStyleSheet()
    body = ParagraphStyle("body", parent=styles["BodyText"], fontSize=8.2, leading=10.4,
                          spaceAfter=3, alignment=TA_LEFT)
    h1 = ParagraphStyle("h1", parent=styles["Heading1"], fontSize=15, leading=17, spaceBefore=4,
                        spaceAfter=5)
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], fontSize=11, leading=13, spaceBefore=7,
                        spaceAfter=3)
    h3 = ParagraphStyle("h3", parent=styles["Heading3"], fontSize=9.2, leading=11, spaceBefore=5,
                        spaceAfter=2)
    cell = ParagraphStyle("cell", parent=body, fontSize=7.2, leading=8.6, spaceAfter=0)

    story = []
    lines = src.read_text(encoding="utf-8").splitlines()
    i = 0
    bullets: list = []

    def flush_bullets():
        nonlocal bullets
        if bullets:
            story.append(ListFlowable([ListItem(Paragraph(b, body), leftIndent=10) for b in bullets],
                                      bulletType="bullet", start="circle", leftIndent=10))
            story.append(Spacer(1, 2))
            bullets = []

    while i < len(lines):
        line = lines[i]
        if line.startswith("|") and i + 1 < len(lines) and set(lines[i + 1].replace("|", "").strip()) <= set("-: "):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not set("".join(cells)) <= set("-: "):
                    rows.append([Paragraph(inline(c), cell) for c in cells])
                i += 1
            flush_bullets()
            width = (A4[0] - 30 * mm) / max(len(rows[0]), 1)
            t = Table(rows, colWidths=[width] * len(rows[0]))
            t.setStyle(TableStyle([
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#999999")),
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eeeeee")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 2),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ]))
            story.append(t)
            story.append(Spacer(1, 4))
            continue
        if line.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            flush_bullets()
            story.append(Preformatted("\n".join(buf), ParagraphStyle(
                "code", parent=body, fontName="Courier", fontSize=7, leading=8.4,
                backColor=colors.HexColor("#f4f4f4"))))
            story.append(Spacer(1, 3))
            continue
        if line.startswith("### "):
            flush_bullets()
            story.append(Paragraph(inline(line[4:]), h3))
        elif line.startswith("## "):
            flush_bullets()
            story.append(Paragraph(inline(line[3:]), h2))
        elif line.startswith("# "):
            flush_bullets()
            story.append(Paragraph(inline(line[2:]), h1))
        elif line.strip() == "---":
            flush_bullets()
            story.append(HRFlowable(width="100%", thickness=0.4, color=colors.HexColor("#bbbbbb"),
                                    spaceBefore=3, spaceAfter=3))
        elif line.startswith("* ") or line.startswith("- "):
            bullets.append(inline(line[2:]))
        elif line.strip():
            flush_bullets()
            story.append(Paragraph(inline(line.strip()), body))
        else:
            flush_bullets()
        i += 1
    flush_bullets()

    doc = SimpleDocTemplate(str(out), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=12 * mm, bottomMargin=12 * mm,
                            title="Cozmo technical report")
    doc.build(story)
    return 0


if __name__ == "__main__":
    raise SystemExit(build(Path(sys.argv[1]), Path(sys.argv[2])))
