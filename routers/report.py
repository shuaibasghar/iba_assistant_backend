"""
Student report: JSON for modal UI; PDF download.
"""

import re

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from services.auth import StudentAuth, get_current_student
from services.student_report_pdf import build_student_report_pdf_bytes
from services.student_report_service import build_student_report

router = APIRouter(prefix="/report", tags=["Report"])


def _safe_filename_part(value: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9._-]+", "_", value.strip()).strip("._-")
    return s[:72] if s else "student"


@router.get("/student/pdf")
async def get_student_report_pdf(student: StudentAuth = Depends(get_current_student)):
    try:
        pdf_bytes = build_student_report_pdf_bytes(student.user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e!s}")

    part = _safe_filename_part(student.roll_number or student.email or "student")
    filename = f"iba-academic-report-{part}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/student")
async def get_student_report(student: StudentAuth = Depends(get_current_student)):
    """
    Full academic summary for the logged-in student.

    Returns:
    - ``full_html``: single HTML document (headings, tables, sections) safe for embedding
    - ``sections``: list of {id, title, html} for section-by-section layout
    - ``charts``: list of chart specs (type, data, keys) for rendering in React
    - ``student``, ``generated_at``: metadata
    """
    try:
        return build_student_report(student.user_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Report failed: {e!s}")
