"""
Permission-checked file exports (CSV, TXT, PDF) with time-limited signed download URLs.

Does not import from agents.* to avoid circular imports with chat tools.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from jose import JWTError, jwt
from pymongo import MongoClient
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from xml.sax.saxutils import escape

from config import get_settings, get_backend_dir


def _get_db():
    s = get_settings()
    c = MongoClient(s.mongodb_url, serverSelectionTimeoutMS=15_000)
    return c[s.mongodb_database]


def _find_student(db, student_id: str) -> dict | None:
    if len(str(student_id)) == 24:
        try:
            st = db["students"].find_one({"_id": ObjectId(student_id)})
            if st:
                return st
        except Exception:
            pass
    st = db["students"].find_one({"roll_number": student_id})
    if st:
        return st
    return db["students"].find_one({"email": student_id})


def get_exports_dir() -> Any:
    s = get_settings()
    d = get_backend_dir() / s.exports_subdir
    d.mkdir(parents=True, exist_ok=True)
    return d


def _now_filename_part() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")


def _safe_filename(s: str) -> str:
    t = re.sub(r"[^a-zA-Z0-9._-]+", "_", s.strip())[:64]
    return t or "export"


def _collect_grades_flat(db, student_oid: ObjectId) -> list[dict[str, Any]]:
    st = db["students"].find_one({"_id": student_oid})
    if not st:
        return []
    student_name = st.get("full_name", "")
    roll = st.get("roll_number", "")
    cgpa = st.get("cgpa")
    grades = list(
        db["grades"].find({"student_id": student_oid}).sort([("semester", 1), ("course_code", 1)])
    )
    rows: list[dict[str, Any]] = []
    for g in grades:
        rows.append(
            {
                "full_name": student_name,
                "roll_number": roll,
                "current_cgpa": cgpa,
                "semester": g.get("semester"),
                "course_code": g.get("course_code"),
                "mid_marks": g.get("mid_marks"),
                "final_marks": g.get("final_marks"),
                "total_marks": g.get("total_marks"),
                "out_of": g.get("out_of"),
                "grade_letter": g.get("grade_letter"),
                "gpa_points": g.get("gpa_points"),
            }
        )
    return rows


def _build_semester_grades_csv(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["message"])
        w.writerow(["No grade records found."])
        return buf.getvalue().encode("utf-8")
    buf = io.StringIO()
    fieldnames = list(rows[0].keys())
    w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _build_semester_grades_txt(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b"No grade records found.\n"
    lines = []
    for r in rows:
        parts = [f"{k}: {r.get(k)}" for k in r if r.get(k) is not None]
        lines.append(" | ".join(str(p) for p in parts))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _escape_pdf(s: str) -> str:
    return escape(str(s or ""), {"'": "&apos;"})


def _build_semester_grades_pdf(rows: list[dict[str, Any]], title: str) -> bytes:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36
    )
    styles = getSampleStyleSheet()
    story = [Paragraph(_escape_pdf(title), styles["Title"]), Spacer(1, 12)]
    if not rows:
        story.append(Paragraph("No grade records found.", styles["Normal"]))
    else:
        keys = list(rows[0].keys())
        h = [Paragraph(f"<b>{_escape_pdf(str(k))}</b>", styles["Normal"]) for k in keys]
        data: list = [h]
        for r in rows:
            data.append(
                [Paragraph(_escape_pdf(str(r.get(k, ""))), styles["Normal"]) for k in keys]
            )
        t = Table(data, repeatRows=1)
        t.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e7ff")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
                ]
            )
        )
        story.append(t)
    doc.build(story)
    return buffer.getvalue()


def _semester_grades_bytes(fmt: str, student_oid: ObjectId) -> tuple[bytes, str, str]:
    db = _get_db()
    rows = _collect_grades_flat(db, student_oid)
    st = db["students"].find_one({"_id": student_oid})
    name = (st or {}).get("full_name", "student")
    base = f"semester-grades-{_safe_filename(name)}-{_now_filename_part()}"
    if fmt == "csv":
        return _build_semester_grades_csv(rows), "text/csv; charset=utf-8", f"{base}.csv"
    if fmt == "txt":
        return _build_semester_grades_txt(rows), "text/plain; charset=utf-8", f"{base}.txt"
    b = _build_semester_grades_pdf(rows, f"Semester grades — {name}")
    return b, "application/pdf", f"{base}.pdf"


def _student_row(doc: dict[str, Any]) -> dict[str, Any]:
    """Serializable profile row (no password fields)."""
    out: dict[str, Any] = {
        "id": str(doc.get("_id", "")),
        "full_name": doc.get("full_name"),
        "email": doc.get("email"),
        "roll_number": doc.get("roll_number"),
        "semester": doc.get("semester"),
        "department": doc.get("department"),
        "batch": doc.get("batch"),
        "cgpa": doc.get("cgpa"),
        "status": doc.get("status"),
        "phone": doc.get("phone"),
        "current_fee_status": doc.get("current_fee_status"),
        "hostel": doc.get("hostel"),
        "university": doc.get("university"),
    }
    for k, v in list(out.items()):
        if v is not None and hasattr(v, "isoformat"):
            try:
                out[k] = v.isoformat()
            except Exception:
                out[k] = str(v)
    return out


def _collect_students_profile_rows(semester: int | None) -> list[dict[str, Any]]:
    db = _get_db()
    flt: dict[str, Any] = {}
    if semester is not None:
        flt["semester"] = int(semester)
    cur = db["students"].find(flt).sort([("department", 1), ("roll_number", 1)])
    return [_student_row(s) for s in cur]


def _build_students_list_csv(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        buf = io.StringIO()
        w = csv.writer(buf)
        w.writerow(["message"])
        w.writerow(["No student records found for this filter."])
        return buf.getvalue().encode("utf-8")
    buf = io.StringIO()
    fieldnames = list(rows[0].keys())
    w = csv.DictWriter(buf, fieldnames=fieldnames, extrasaction="ignore")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode("utf-8")


def _build_students_list_txt(rows: list[dict[str, Any]]) -> bytes:
    if not rows:
        return b"No student records found for this filter.\n"
    lines = ["\t".join(str(k) for k in rows[0].keys())]
    for r in rows:
        lines.append("\t".join("" if v is None else str(v) for v in r.values()))
    return ("\n".join(lines) + "\n").encode("utf-8")


def _build_students_list_pdf(rows: list[dict[str, Any]], title: str) -> bytes:
    if not rows:
        return _build_semester_grades_pdf([], title)  # empty
    return _build_semester_grades_pdf(
        [
            {str(k): ("" if v is None else v) for k, v in r.items()}
            for r in rows
        ],
        title,
    )


def _students_profile_bytes(
    fmt: str, *, semester: int | None, label: str
) -> tuple[bytes, str, str]:
    rows = _collect_students_profile_rows(semester)
    base = f"students-{_safe_filename(label)}-{_now_filename_part()}"
    if fmt == "csv":
        return _build_students_list_csv(rows), "text/csv; charset=utf-8", f"{base}.csv"
    if fmt == "txt":
        return _build_students_list_txt(rows), "text/plain; charset=utf-8", f"{base}.txt"
    b = _build_students_list_pdf(rows, f"Students — {label} ({len(rows)} rows)")
    return b, "application/pdf", f"{base}.pdf"


# Superadmin-only bulk / directory export kinds
BULK_STUDENT_EXPORT_KINDS = frozenset({"all_students_profile", "students_by_semester"})

KIND_META: dict[str, dict[str, Any]] = {
    "semester_grades_detail": {
        "allowed_roles": frozenset({"student", "superadmin", "superuser"}),
        "label": "All semester / course grade rows for one student",
    },
    "all_students_profile": {
        "allowed_roles": frozenset({"superadmin", "superuser"}),
        "label": "Every student: profile row per student (full directory export)",
    },
    "students_by_semester": {
        "allowed_roles": frozenset({"superadmin", "superuser"}),
        "label": "All students in a program semester (uses students.semester field)",
    },
}


def _normalize_role(r: str) -> str:
    x = (r or "").strip().lower()
    if x == "superuser":
        return "superadmin"
    return x


def resolve_student_oid_for_export(
    *,
    actor_user_id: str,
    role: str,
    target_student_id: str | None,
) -> ObjectId:
    db = _get_db()
    r = _normalize_role(role)
    st_self = _find_student(db, actor_user_id)

    if r == "student" or (st_self and r not in ("superadmin", "superuser")):
        if not st_self:
            raise PermissionError("Only students can use this export with a student account.")
        sid: ObjectId = st_self["_id"]
        if not target_student_id or not str(target_student_id).strip():
            return sid
        t = str(target_student_id).strip()
        if str(sid) == t or st_self.get("roll_number") == t:
            return sid
        if (st_self.get("email") or "").lower() == t.lower():
            return sid
        try:
            if ObjectId(t) == sid:
                return sid
        except Exception:
            pass
        raise PermissionError("You may only download your own academic export.")

    if r in ("superadmin", "superuser"):
        if not target_student_id or not str(target_student_id).strip():
            raise ValueError(
                "For one student’s **grades** export, set target_student_id (roll, email, or student id). "
                "For a **full list** of students, use export_kind=all_students_profile or "
                "students_by_semester with filter_semester (no target needed)."
            )
        tgt = _find_student(db, str(target_student_id).strip())
        if not tgt:
            raise ValueError(f"No student found for: {target_student_id!r}.")
        return tgt["_id"]

    raise PermissionError(
        f"Role {role!r} cannot use this export. Students: own data. Superadmin: set target student."
    )


def check_export_kind_allowed(kind: str, role: str) -> None:
    meta = KIND_META.get(kind)
    if not meta:
        raise ValueError(
            f"Unknown export kind {kind!r}. Supported: {', '.join(sorted(KIND_META.keys()))}"
        )
    r = _normalize_role(role)
    if r == "superuser":
        r = "superadmin"
    allowed: frozenset = meta["allowed_roles"]
    if r not in allowed:
        raise PermissionError(
            f"Your role may not use export {kind!r}. Allowed: {sorted(allowed)}"
        )


def _store_bytes(
    b: bytes, download_name: str, media_type: str
) -> tuple[bytes, str, str, str]:
    file_id = f"{uuid.uuid4().hex}_{download_name.replace('/', '_')}"
    p = get_exports_dir() / file_id
    p.write_bytes(b)
    return b, media_type, download_name, file_id


def generate_export_file(
    *, kind: str, format: str, student_oid: ObjectId
) -> tuple[bytes, str, str, str]:
    f = (format or "csv").strip().lower()
    if f not in ("csv", "txt", "pdf"):
        raise ValueError("format must be csv, txt, or pdf")
    if kind != "semester_grades_detail":
        raise ValueError("Use generate_bulk_student_export for directory exports")
    b, mt, name = _semester_grades_bytes(f, student_oid)
    return _store_bytes(b, name, mt)


def generate_bulk_student_export(
    *, kind: str, format: str, filter_semester: int | None
) -> tuple[bytes, str, str, str]:
    f = (format or "csv").strip().lower()
    if f not in ("csv", "txt", "pdf"):
        raise ValueError("format must be csv, txt, or pdf")
    if kind == "all_students_profile":
        b, mt, name = _students_profile_bytes(
            f, semester=None, label="all"
        )
    elif kind == "students_by_semester":
        if filter_semester is None:
            raise ValueError(
                "students_by_semester requires filter_semester (e.g. 3 for third semester)."
            )
        b, mt, name = _students_profile_bytes(
            f, semester=int(filter_semester), label=f"semester-{int(filter_semester)}"
        )
    else:
        raise ValueError(f"Not a bulk student export kind: {kind!r}")
    return _store_bytes(b, name, mt)


def mint_export_download_token(
    file_id: str, subject_user_id: str, role: str, filename: str, media_type: str
) -> str:
    s = get_settings()
    exp_ts = int(
        (datetime.now(timezone.utc) + timedelta(hours=s.export_download_token_expire_hours)).timestamp()
    )
    payload = {
        "sub": str(subject_user_id),
        "role": str(role).lower(),
        "file_id": str(file_id),
        "filename": str(filename)[:200],
        "mime": str(media_type)[:120],
        "purpose": "export_download",
        "exp": exp_ts,
    }
    return jwt.encode(payload, s.jwt_secret_key, algorithm=s.jwt_algorithm)


def verify_export_download_token(token: str) -> dict[str, Any]:
    s = get_settings()
    try:
        payload = jwt.decode(token, s.jwt_secret_key, algorithms=[s.jwt_algorithm])
    except JWTError as e:
        raise ValueError("Invalid or expired download link") from e
    if payload.get("purpose") != "export_download":
        raise ValueError("Invalid token purpose")
    if not payload.get("file_id"):
        raise ValueError("Invalid token: missing file_id")
    return payload


def build_export_download_url(public_base: str, token: str) -> str:
    base = (public_base or "").rstrip("/")
    from urllib.parse import quote

    return f"{base}/exports/download?token={quote(token, safe='')}"


def run_export_for_chat(
    *,
    actor_user_id: str,
    actor_role: str,
    export_kind: str,
    file_format: str,
    target_student_id: str | None = None,
    filter_semester: int | None = None,
    public_api_base: str | None = None,
) -> dict[str, Any]:
    check_export_kind_allowed(export_kind, actor_role)
    s = get_settings()
    base = (public_api_base or s.public_api_base_url or "").rstrip("/")

    one_student_oid: ObjectId | None = None
    if export_kind in BULK_STUDENT_EXPORT_KINDS:
        b, media_type, fname, file_id = generate_bulk_student_export(
            kind=export_kind,
            format=file_format,
            filter_semester=filter_semester,
        )
    else:
        one_student_oid = resolve_student_oid_for_export(
            actor_user_id=actor_user_id,
            role=actor_role,
            target_student_id=target_student_id,
        )
        b, media_type, fname, file_id = generate_export_file(
            kind=export_kind, format=file_format, student_oid=one_student_oid
        )
    _ = b

    token = mint_export_download_token(
        file_id=file_id,
        subject_user_id=actor_user_id,
        role=actor_role,
        filename=fname,
        media_type=media_type,
    )
    url = build_export_download_url(base or "http://localhost:8000", token)
    st_label = "export"
    if export_kind in BULK_STUDENT_EXPORT_KINDS:
        if export_kind == "all_students_profile":
            n = _get_db()["students"].count_documents({})
            st_label = f"all students ({n} rows)" if n else "no students"
        else:
            sem = int(filter_semester) if filter_semester is not None else -1
            n = _get_db()["students"].count_documents({"semester": sem})
            st_label = f"semester {filter_semester} ({n} students)"
    else:
        assert one_student_oid is not None
        st = _get_db()["students"].find_one({"_id": one_student_oid})
        st_label = (st or {}).get("full_name") or (st or {}).get("roll_number") or str(one_student_oid)
    return {
        "success": True,
        "export_kind": export_kind,
        "format": file_format,
        "filename": fname,
        "download_url": url,
        "message": (
            f"File is ready. Open this link to download (expires in {s.export_download_token_expire_hours} hour(s)): {url}"
        ),
        "student_label": st_label,
    }
