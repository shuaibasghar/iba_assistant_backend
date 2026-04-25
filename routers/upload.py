"""
Generic file upload: accept any file, persist under backend/uploads/received/.
"""

import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile

from config import get_backend_dir, get_settings

router = APIRouter(tags=["Upload"])


@router.post("/upload")
async def receive_upload(
    file: UploadFile = File(..., description="Any file; stored on the server as-is"),
):
    """Store the uploaded bytes in a local directory (no type restriction)."""
    settings = get_settings()
    max_b = settings.generic_upload_max_mb * 1024 * 1024
    body = await file.read()
    if len(body) > max_b:
        raise HTTPException(
            status_code=400,
            detail=f"File too large (max {settings.generic_upload_max_mb} MB).",
        )

    raw_name = (file.filename or "").strip()
    base_name = Path(raw_name).name if raw_name else ""
    if not base_name or base_name in (".", ".."):
        base_name = "file"

    dest_dir = get_backend_dir() / settings.upload_receive_subdir
    dest_dir.mkdir(parents=True, exist_ok=True)

    suffix = Path(base_name).suffix
    stem = Path(base_name).stem
    if not stem:
        stem = "file" if not suffix else "unnamed"

    unique = f"{uuid.uuid4().hex[:10]}_{stem}{suffix}"
    dest_path = dest_dir / unique
    dest_path.write_bytes(body)

    rel = dest_path.relative_to(get_backend_dir())
    return {
        "saved_as": unique,
        "size_bytes": len(body),
        "content_type": file.content_type,
        "path": rel.as_posix(),
    }
