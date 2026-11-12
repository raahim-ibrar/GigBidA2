"""Render the reviewed Markdown technical narrative as a standalone PDF."""

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


def build():
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="Narrative",
            fontName="Helvetica",
            fontSize=10,
            leading=15,
            spaceAfter=10,
            textColor=colors.HexColor("#242031"),
        )
    )
    styles.add(
        ParagraphStyle(
            name="NarrativeHeading",
            fontName="Helvetica-Bold",
            fontSize=14,
            leading=19,
            spaceBefore=14,
            spaceAfter=9,
            textColor=colors.HexColor("#7048aa"),
            keepWithNext=True,
        )
    )
    styles.add(
        ParagraphStyle(
            name="NarrativeTitle",
            fontName="Helvetica-Bold",
            fontSize=23,
            leading=29,
            spaceAfter=18,
            textColor=colors.HexColor("#7048aa"),
        )
    )
    text = Path("docs/TECHNICAL_WRITEUP.md").read_text(encoding="utf-8")
    story = []
    for block in text.split("\n\n"):
        if not block.strip():
            continue
        if block.startswith("# "):
            story.append(Paragraph(escape(block[2:]), styles["NarrativeTitle"]))
            story.append(Paragraph("Raahim / AI-4016 / November 2026", styles["Narrative"]))
            story.append(Spacer(1, 4 * mm))
        elif block.startswith("## "):
            story.append(Paragraph(escape(block[3:]), styles["NarrativeHeading"]))
        else:
            story.append(Paragraph(escape(block.replace("`", "")), styles["Narrative"]))

    def footer(canvas, doc):
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.HexColor("#645e73"))
        canvas.drawString(
            20 * mm, 12 * mm, "GigBid / Technical narrative / measured synthetic research"
        )
        canvas.drawRightString(A4[0] - 20 * mm, 12 * mm, str(doc.page))

    target = Path("output/pdf/GigBid_Technical_Writeup.pdf")
    target.parent.mkdir(parents=True, exist_ok=True)
    SimpleDocTemplate(
        str(target),
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=23 * mm,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        title="GigBid technical narrative",
        author="Raahim",
    ).build(story, onFirstPage=footer, onLaterPages=footer)
    print(target.resolve())


if __name__ == "__main__":
    build()
