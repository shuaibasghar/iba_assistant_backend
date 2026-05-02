"""
Time-limited signed download for generated exports (e.g. grade CSV from chat).
"""

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse

from services.portal_export_service import get_exports_dir, verify_export_download_token

router = APIRouter(prefix="/api/exports", tags=["Exports"])


@router.get("/download")
async def download_export(token: str = Query(..., min_length=20)):
    try:
        p = verify_export_download_token(token)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    path = get_exports_dir() / p["file_id"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="File missing or no longer on server")

    name = p.get("filename") or "export"
    media = p.get("mime") or "application/octet-stream"
    return FileResponse(
        str(path),
        media_type=media,
        filename=name,
        headers={"Content-Disposition": f'attachment; filename="{name}"'},
    )
