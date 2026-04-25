"""
PDF report: tables then chart per section. Uses BytesIO for ReportLab Image (not ImageReader).
"""

from __future__ import annotations

import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from services.student_report_service import collect_student_report_data


def _chart_to_png(chart: dict[str, Any]) -> bytes | None:
    fig, ax = plt.subplots(figsize=(6.4, 3.35), dpi=115)
    fig.patch.set_facecolor("white")

    ctype = chart.get("type")
    if ctype == "pie":
        slices = chart.get("slices") or []
        if not slices:
            plt.close(fig)
            return None
        labels = [s["name"] for s in slices]
        values = [s["value"] for s in slices]
        pal = chart.get("colors") or []
        colors_mpl = [pal[i % len(pal)] for i in range(len(values))] if pal else None
        ax.pie(
            values,
            labels=labels,
            colors=colors_mpl,
            autopct=lambda pct: f"{pct:.0f}%" if pct >= 6 else "",
            startangle=90,
            textprops={"fontsize": 9},
        )
        ax.set_title(chart.get("title") or "", fontsize=11, pad=10)
    elif ctype == "grouped_bar":
        labels = chart.get("labels") or []
        series = chart.get("series") or []
        if not labels or not series:
            plt.close(fig)
            return None
        x = range(len(labels))
        n = len(series)
        width = 0.8 / max(n, 1)
        for i, s in enumerate(series):
            offset = (i - (n - 1) / 2) * width
            ax.bar(
                [xi + offset for xi in x],
                s.get("values") or [],
                width,
                label=s.get("name"),
                color=s.get("color") or "#6366f1",
            )
        ax.set_xticks(list(x))
        ax.set_xticklabels(labels, rotation=18, ha="right", fontsize=8)
        ax.legend(fontsize=8, loc="upper right")
        ax.set_title(chart.get("title") or "", fontsize=11, pad=10)
        ax.yaxis.grid(True, linestyle="--", alpha=0.35)
        ax.set_axisbelow(True)
    elif ctype == "bar":
        labels = chart.get("labels") or []
        values = chart.get("values") or []
        if not labels:
            plt.close(fig)
            return None
        xpos = range(len(labels))
        ax.bar(xpos, values, color=chart.get("color") or "#4f46e5", width=0.55)
        ax.set_xticks(list(xpos))
        ax.set_xticklabels(labels, rotation=18, ha="right", fontsize=8)
        ax.set_ylabel("SGPA", fontsize=9)
        ax.set_title(chart.get("title") or "", fontsize=11, pad=10)
        ax.yaxis.grid(True, linestyle="--", alpha=0.35)
        ax.set_axisbelow(True)
    else:
        plt.close(fig)
        return None

    fig.tight_layout()
    out = io.BytesIO()
    fig.savefig(out, format="png", bbox_inches="tight", facecolor="white", edgecolor="none")
    plt.close(fig)
    return out.getvalue()


def build_student_report_pdf_bytes(student_id: str) -> bytes:
    data = collect_student_report_data(student_id)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=0.72 * inch,
        rightMargin=0.72 * inch,
        topMargin=0.6 * inch,
        bottomMargin=0.6 * inch,
        title="Student academic report",
    )
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "RepTitle",
        parent=styles["Heading1"],
        fontSize=16,
        spaceAfter=6,
        textColor=colors.HexColor("#1e1b4b"),
    )
    h2_style = ParagraphStyle(
        "RepH2",
        parent=styles["Heading2"],
        fontSize=11.5,
        spaceBefore=12,
        spaceAfter=6,
        textColor=colors.HexColor("#312e81"),
    )
    body_style = ParagraphStyle(
        "RepBody",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        spaceAfter=4,
    )
    note_style = ParagraphStyle(
        "RepNote",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        spaceAfter=4,
        textColor=colors.HexColor("#9a3412"),
    )
    highlight_style = ParagraphStyle(
        "RepHi",
        parent=styles["Normal"],
        fontSize=9,
        leading=12,
        spaceAfter=4,
        backColor=colors.HexColor("#eef2ff"),
        borderPadding=6,
        leftIndent=4,
        rightIndent=4,
    )

    story: list = []
    story.append(Paragraph(escape("Student academic report"), title_style))
    meta_bits: list[str] = []
    if data.student.get("full_name"):
        meta_bits.append(str(data.student["full_name"]))
    if data.student.get("roll_number"):
        meta_bits.append(str(data.student["roll_number"]))
    meta_bits.append(f"Generated {data.generated_at}")
    story.append(Paragraph(escape(" · ".join(meta_bits)), body_style))
    story.append(Spacer(1, 0.12 * inch))

    for sec in data.sections:
        story.append(Paragraph(escape(sec.title), h2_style))
        for i, para in enumerate(sec.paragraphs):
            if sec.id == "fees" and i > 0:
                st = note_style
            elif sec.id == "exams" and i > 0:
                st = highlight_style
            else:
                st = body_style
            story.append(Paragraph(escape(para).replace("\n", "<br/>"), st))

        if sec.headers and sec.rows:
            tbl_data: list[list[str]] = [
                [escape(str(h)) for h in sec.headers],
                *[[escape(str(c)) for c in row] for row in sec.rows],
            ]
            t = Table(tbl_data, repeatRows=1)
            t.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e7ff")),
                        ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1e1b4b")),
                        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                        ("FONTSIZE", (0, 0), (-1, -1), 7),
                        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c7d2fe")),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ]
                )
            )
            story.append(Spacer(1, 0.06 * inch))
            story.append(t)

        if sec.chart:
            png = _chart_to_png(sec.chart)
            if png:
                story.append(Spacer(1, 0.1 * inch))
                iw, ih = PILImage.open(io.BytesIO(png)).size
                target_w = 6.1 * inch
                target_h = target_w * (ih / float(iw))
                max_h = 3.1 * inch
                if target_h > max_h:
                    target_h = max_h
                    target_w = target_h * (float(iw) / ih)
                story.append(Image(io.BytesIO(png), width=target_w, height=target_h))

    doc.build(story)
    pdf = buffer.getvalue()
    buffer.close()
    return pdf
