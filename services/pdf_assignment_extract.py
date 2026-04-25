"""
Extract assignment metadata from PDF text (opened on / closed on / due, title hints, marks).
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from dateutil import parser as date_parser

try:
    from pypdf import PdfReader
except ImportError:  # pragma: no cover
    PdfReader = None  # type: ignore

MAX_PAGES_DEFAULT = 6
MAX_TEXT_CHARS = 12000

_OPEN_RE = re.compile(
    r"(?im)^[^\n]*?(?:opened\s+on|opens?\s+on|open\s+from|available\s+from|"
    r"assignment\s+opens|start\s+date|release\s+date)\s*[:\-]?\s*(.+?)\s*$"
)
_CLOSE_RE = re.compile(
    r"(?im)^[^\n]*?(?:closed\s+on|closes?\s+on|closing\s+(?:date|time)|"
    r"due\s+date|deadline|submit\s+(?:by|before)|submission\s+(?:deadline|closes)|"
    r"last\s+date|end\s+date)\s*[:\-]?\s*(.+?)\s*$"
)
_MARKS_RE = re.compile(r"(?im)(?:total\s+marks?|marks?|points?)\s*[:\-]?\s*(\d{1,4})\b")
_TITLE_LINE_RE = re.compile(r"(?im)^(?:assignment|title|homework)\s*[:\-]\s*(.+)$")


def _extract_pdf_text(pdf_bytes: bytes, max_pages: int = MAX_PAGES_DEFAULT) -> str:
    if PdfReader is None:
        raise RuntimeError("pypdf is not installed")
    reader = PdfReader(BytesIO(pdf_bytes))
    parts: list[str] = []
    n = min(len(reader.pages), max_pages)
    for i in range(n):
        page = reader.pages[i]
        t = page.extract_text()
        if t:
            parts.append(t)
    text = "\n".join(parts).strip()
    return text[:MAX_TEXT_CHARS]


def _parse_datetime_fragment(fragment: str) -> datetime | None:
    frag = fragment.strip().strip(".,;:")
    if not frag:
        return None
    frag = re.sub(r"\s+", " ", frag)
    try:
        dt = date_parser.parse(frag, fuzzy=True, dayfirst=False)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError, OverflowError):
        return None


def _first_match_dt(pattern: re.Pattern, text: str) -> datetime | None:
    m = pattern.search(text)
    if not m:
        return None
    return _parse_datetime_fragment(m.group(1))


def _title_hint(text: str) -> str | None:
    for line in text.splitlines():
        s = line.strip()
        if not s or len(s) < 4:
            continue
        tm = _TITLE_LINE_RE.match(s)
        if tm:
            t = tm.group(1).strip()
            if t:
                return t[:200]
        if len(s) > 8 and not s.lower().startswith("page "):
            return s[:200]
    return None


def _marks_hint(text: str) -> int | None:
    m = _MARKS_RE.search(text)
    if not m:
        return None
    try:
        v = int(m.group(1))
        return v if 1 <= v <= 1000 else None
    except ValueError:
        return None


def analyze_assignment_pdf(pdf_bytes: bytes) -> dict[str, Any]:
    """
    Read PDF text and infer opened_on / closed_on (submission deadline), optional title & marks.

    Returns ISO8601 strings in UTC where datetimes are found.
    """
    text = _extract_pdf_text(pdf_bytes)
    if not text:
        return {
            "opened_on": None,
            "closed_on": None,
            "title_hint": None,
            "marks_hint": None,
            "raw_text_preview": "",
            "note": "No extractable text in PDF (may be scanned). Fill dates manually.",
        }

    opened = _first_match_dt(_OPEN_RE, text)
    closed = _first_match_dt(_CLOSE_RE, text)

    if closed is None:
        iso_like = re.findall(
            r"\b(\d{4}-\d{2}-\d{2}(?:[ T]\d{1,2}:\d{2}(?::\d{2})?)?)\b",
            text,
        )
        for candidate in iso_like[-3:]:
            dt = _parse_datetime_fragment(candidate)
            if dt:
                closed = dt
                break

    return {
        "opened_on": opened.isoformat() if opened else None,
        "closed_on": closed.isoformat() if closed else None,
        "title_hint": _title_hint(text),
        "marks_hint": _marks_hint(text),
        "raw_text_preview": text[:800].replace("\r", " "),
    }
