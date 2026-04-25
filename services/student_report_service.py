"""
Student academic report: shared data collection, HTML/JSON, and per-section charts.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from agents.tools.database_tools import (
    AssignmentQueryTool,
    ExamQueryTool,
    FeeQueryTool,
    GradeQueryTool,
    find_student,
    get_db,
)


def _escape(s: Any) -> str:
    if s is None:
        return ""
    return html.escape(str(s))


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    th = "".join(f"<th>{_escape(h)}</th>" for h in headers)
    body_rows = []
    for row in rows:
        tds = "".join(f"<td>{_escape(c)}</td>" for c in row)
        body_rows.append(f"<tr>{tds}</tr>")
    return (
        '<table class="report-table"><thead><tr>'
        f"{th}</tr></thead><tbody>{''.join(body_rows)}</tbody></table>"
    )


def _section_block(title: str, inner: str) -> str:
    return (
        f'<section class="report-section" data-section="{_escape(title)}">'
        f'<h2 class="report-h2">{_escape(title)}</h2>'
        f'<div class="report-section-inner">{inner}</div></section>'
    )


def _p(text: str, cls: str = "report-p") -> str:
    return f'<p class="{cls}">{_escape(text)}</p>'


def _json_table_cell(v: Any) -> Any:
    """JSON-serialize a table cell for the frontend (no datetimes/objects leaking)."""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    if hasattr(v, "isoformat"):
        try:
            return v.isoformat()
        except Exception:
            return str(v)
    return str(v)


def _section_api_dict(sec: ReportSectionData) -> dict[str, Any]:
    """Section payload for JSON clients: structured paragraphs + table + legacy html."""
    table_payload = None
    if sec.headers and sec.rows:
        table_payload = {
            "headers": [str(h) for h in sec.headers],
            "rows": [[_json_table_cell(c) for c in row] for row in sec.rows],
        }
    return {
        "id": sec.id,
        "title": sec.title,
        "paragraphs": list(sec.paragraphs),
        "table": table_payload,
        "html": _section_to_html(sec),
    }


@dataclass
class ReportSectionData:
    id: str
    title: str
    paragraphs: list[str]
    headers: list[str] | None = None
    rows: list[list[Any]] | None = None
    chart: dict[str, Any] | None = None


@dataclass
class StudentReportData:
    student: dict[str, Any]
    generated_at: str
    sections: list[ReportSectionData] = field(default_factory=list)


def collect_student_report_data(student_id: str) -> StudentReportData:
    student_doc = find_student(get_db(), student_id)
    if not student_doc:
        raise ValueError("Student not found")

    assign_tool = AssignmentQueryTool()
    fee_tool = FeeQueryTool()
    exam_tool = ExamQueryTool()
    grade_tool = GradeQueryTool()

    assignments = assign_tool._run(student_id)
    fees = fee_tool._run(student_id)
    exams = exam_tool._run(student_id)
    grades = grade_tool._run(student_id)

    for block in (assignments, fees, exams, grades):
        if block.get("error"):
            raise ValueError(block["error"])

    summ = assignments.get("summary") or {}
    assign_rows: list[list[Any]] = []

    def _extend_assign(items: list, status: str) -> None:
        for it in items or []:
            assign_rows.append(
                [
                    it.get("title"),
                    it.get("course_code"),
                    it.get("due_date") or "—",
                    status,
                    it.get("marks_obtained") if it.get("marks_obtained") is not None else "—",
                ]
            )

    _extend_assign(assignments.get("pending"), "Pending")
    _extend_assign(assignments.get("submitted"), "Submitted")
    _extend_assign(assignments.get("overdue"), "Overdue")
    _extend_assign(assignments.get("upcoming"), "Upcoming")

    assign_intro = (
        f"Pending: {summ.get('total_pending', 0)}, submitted: {summ.get('total_submitted', 0)}, "
        f"overdue: {summ.get('total_overdue', 0)}, upcoming: {summ.get('total_upcoming', 0)}."
    )

    pie_assign = [
        {"name": "Pending", "value": int(summ.get("total_pending", 0) or 0)},
        {"name": "Submitted", "value": int(summ.get("total_submitted", 0) or 0)},
        {"name": "Overdue", "value": int(summ.get("total_overdue", 0) or 0)},
        {"name": "Upcoming", "value": int(summ.get("total_upcoming", 0) or 0)},
    ]
    pie_assign = [x for x in pie_assign if x["value"] > 0]
    assign_chart = None
    if pie_assign:
        assign_chart = {
            "type": "pie",
            "title": "Assignments by status",
            "slices": pie_assign,
            "colors": ["#6366f1", "#22c55e", "#ef4444", "#f59e0b"],
        }

    hist = fees.get("payment_history") or []
    cf = fees.get("current_fee_status") or {}
    fee_intro = (
        f"Current semester status: {cf.get('status')}. "
        f"Documents: {'eligible' if fees.get('can_access_documents') else 'blocked until dues are clear'}."
    )
    fee_note = fees.get("message") or ""

    fee_rows = [
        [
            r.get("semester"),
            r.get("amount_due"),
            r.get("amount_paid"),
            r.get("balance"),
            r.get("status"),
            r.get("payment_date") or "—",
            r.get("challan_number") or "—",
        ]
        for r in hist
    ]

    fee_chart = None
    fee_labels: list[str] = []
    paid_vals: list[float] = []
    balance_vals: list[float] = []
    for r in hist:
        fee_labels.append(f"Sem {r.get('semester')}")
        paid_vals.append(float(r.get("amount_paid") or 0))
        balance_vals.append(float(r.get("balance") or 0))
    if fee_labels:
        fee_chart = {
            "type": "grouped_bar",
            "title": "Fee paid vs balance by semester",
            "labels": fee_labels,
            "series": [
                {"name": "Paid", "values": paid_vals, "color": "#22c55e"},
                {"name": "Balance", "values": balance_vals, "color": "#f97316"},
            ],
        }

    ex_intro = f"Upcoming exams this semester: {exams.get('total_upcoming_exams', 0)}."
    exam_paragraphs: list[str] = [ex_intro]
    first = exams.get("first_upcoming_exam")
    if first:
        exam_paragraphs.append(
            f"Next: {first.get('course_code')} ({first.get('exam_type')}) on "
            f"{first.get('exam_date')} at {first.get('start_time')} — {first.get('venue')}."
        )

    exam_rows: list[list[Any]] = []
    for label, key in (("Mid-term", "mid_term_exams"), ("Final", "final_exams")):
        for it in exams.get(key) or []:
            exam_rows.append(
                [
                    label,
                    it.get("course_code"),
                    it.get("course_name"),
                    it.get("exam_date"),
                    it.get("start_time"),
                    it.get("venue"),
                    it.get("days_until_exam"),
                ]
            )

    cgpa = grades.get("current_cgpa")
    if cgpa is None:
        cgpa = student_doc.get("cgpa")
    sem = fees.get("current_semester") or student_doc.get("semester")
    g_intro = f"CGPA: {cgpa}. Semesters with grades: {grades.get('total_semesters_completed', 0)}."

    grade_rows: list[list[Any]] = []
    sgpa_labels: list[str] = []
    sgpa_values: list[float] = []
    for block in grades.get("semesters") or []:
        s = block.get("semester")
        sgpa = float(block.get("semester_gpa") or 0)
        sgpa_labels.append(f"Sem {s}")
        sgpa_values.append(sgpa)
        for c in block.get("courses") or []:
            grade_rows.append(
                [
                    s,
                    c.get("course_code"),
                    c.get("mid_marks"),
                    c.get("final_marks"),
                    c.get("total_marks"),
                    c.get("out_of"),
                    c.get("grade_letter"),
                    c.get("gpa_points"),
                    block.get("semester_gpa"),
                ]
            )

    grades_chart = None
    if sgpa_labels:
        grades_chart = {
            "type": "bar",
            "title": "SGPA by semester",
            "labels": sgpa_labels,
            "values": sgpa_values,
            "color": "#4f46e5",
        }

    student_name = (
        grades.get("student_name")
        or fees.get("student_name")
        or student_doc.get("full_name")
        or "Student"
    )
    roll = grades.get("roll_number") or student_doc.get("roll_number") or ""
    dept = student_doc.get("department") or ""
    batch = student_doc.get("batch") or ""

    overview_lines = [
        f"{student_name}" + (f" · {roll}" if roll else ""),
        f"{dept}" + (f" · Batch {batch}" if batch else "") + f" · Semester {sem} · CGPA {cgpa}",
    ]

    generated = datetime.now(timezone.utc).isoformat()

    sections: list[ReportSectionData] = [
        ReportSectionData(id="overview", title="Profile overview", paragraphs=overview_lines),
        ReportSectionData(
            id="assignments",
            title="Assignments",
            paragraphs=[assign_intro],
            headers=["Assignment", "Course", "Due", "Status", "Marks"] if assign_rows else None,
            rows=assign_rows if assign_rows else None,
            chart=assign_chart,
        ),
        ReportSectionData(
            id="fees",
            title="Fees & payments",
            paragraphs=[fee_intro] + ([fee_note] if fee_note else []),
            headers=["Semester", "Due", "Paid", "Balance", "Status", "Paid on", "Challan"]
            if fee_rows
            else None,
            rows=fee_rows if fee_rows else None,
            chart=fee_chart,
        ),
        ReportSectionData(
            id="exams",
            title="Exam schedule",
            paragraphs=exam_paragraphs,
            headers=["Type", "Code", "Course", "Date", "Time", "Venue", "Days left"]
            if exam_rows
            else None,
            rows=exam_rows if exam_rows else None,
        ),
        ReportSectionData(
            id="grades",
            title="Grades & SGPA",
            paragraphs=[g_intro],
            headers=[
                "Sem",
                "Course",
                "Mid",
                "Final",
                "Total",
                "Out of",
                "Grade",
                "Points",
                "SGPA",
            ]
            if grade_rows
            else None,
            rows=grade_rows if grade_rows else None,
            chart=grades_chart,
        ),
        ReportSectionData(
            id="documents",
            title="Documents",
            paragraphs=[
                fee_note or "Contact the registrar for transcripts and certificates."
            ],
        ),
    ]

    for sec in sections:
        if sec.id == "assignments" and not assign_rows:
            sec.paragraphs = sec.paragraphs + ["No assignment records for the current scope."]
        if sec.id == "fees" and not fee_rows:
            sec.paragraphs = sec.paragraphs + ["No fee records."]
        if sec.id == "exams" and not exam_rows:
            sec.paragraphs = sec.paragraphs + ["No upcoming exams scheduled."]
        if sec.id == "grades" and not grade_rows:
            sec.paragraphs = sec.paragraphs + ["No grade records."]

    return StudentReportData(
        student={
            "full_name": student_doc.get("full_name"),
            "roll_number": student_doc.get("roll_number"),
            "department": student_doc.get("department"),
            "batch": student_doc.get("batch"),
            "cgpa": cgpa,
            "semester": sem,
        },
        generated_at=generated,
        sections=sections,
    )


def _section_to_html(sec: ReportSectionData) -> str:
    parts: list[str] = []
    for i, line in enumerate(sec.paragraphs):
        if sec.id == "fees" and i > 0:
            cls = "report-note"
        elif sec.id == "exams" and i > 0:
            cls = "report-highlight"
        else:
            cls = "report-p"
        parts.append(_p(line, cls))
    if sec.headers and sec.rows:
        parts.append(_table(sec.headers, sec.rows))
    return "".join(parts)


def build_student_report(student_id: str) -> dict[str, Any]:
    data = collect_student_report_data(student_id)

    sections_out: list[dict[str, Any]] = []
    charts_flat: list[dict[str, Any]] = []

    for sec in data.sections:
        sections_out.append(_section_api_dict(sec))
        if not sec.chart:
            continue
        c = sec.chart
        sid = sec.id
        if c["type"] == "pie":
            charts_flat.append(
                {
                    "id": f"{sid}_chart",
                    "section_id": sid,
                    "title": c.get("title", ""),
                    "type": "pie",
                    "nameKey": "name",
                    "valueKey": "value",
                    "data": c["slices"],
                    "colors": c.get("colors", []),
                }
            )
        elif c["type"] == "grouped_bar":
            rows = []
            for i, lab in enumerate(c["labels"]):
                row: dict[str, Any] = {"name": lab}
                for s in c["series"]:
                    row[s["name"].lower().replace(" ", "_")] = s["values"][i]
                rows.append(row)
            bar_defs = []
            for s in c["series"]:
                key = s["name"].lower().replace(" ", "_")
                bar_defs.append({"dataKey": key, "name": s["name"], "fill": s["color"]})
            charts_flat.append(
                {
                    "id": f"{sid}_chart",
                    "section_id": sid,
                    "title": c.get("title", ""),
                    "type": "bar",
                    "xAxisKey": "name",
                    "bars": bar_defs,
                    "data": rows,
                }
            )
        elif c["type"] == "bar":
            bar_data = [
                {"name": c["labels"][i], "sgpa": c["values"][i]}
                for i in range(len(c["labels"]))
            ]
            charts_flat.append(
                {
                    "id": f"{sid}_chart",
                    "section_id": sid,
                    "title": c.get("title", ""),
                    "type": "bar",
                    "xAxisKey": "name",
                    "bars": [{"dataKey": "sgpa", "name": "SGPA", "fill": c.get("color", "#6366f1")}],
                    "data": bar_data,
                }
            )

    wrapped_blocks = [_section_block(s["title"], s["html"]) for s in sections_out]
    header = (
        f'<header class="report-doc-header">'
        f'<h1 class="report-h1">Student academic report</h1>'
        f'<p class="report-generated">Generated: {_escape(data.generated_at)}</p>'
        f"</header>"
    )
    full_html = (
        f'<article class="report-document">{header}'
        f'<div class="report-body">{"".join(wrapped_blocks)}</div></article>'
    )

    return {
        "student": data.student,
        "generated_at": data.generated_at,
        "sections": sections_out,
        "charts": charts_flat,
        "full_html": full_html,
    }
