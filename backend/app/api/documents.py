"""Document version listing + download (Phase 3).

Read-only. Writing a new version only ever happens via the Executor, triggered
from POST /api/approvals/{id}/decide.
"""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app.db.models import DocumentVersion
from app.db.postgres_client import get_db
from app.models.approval import DocumentVersionOut

router = APIRouter(prefix="/api/documents", tags=["documents"])


@router.get("/contract/{contract_id}/versions", response_model=list[DocumentVersionOut])
def list_versions(contract_id: str, db: Session = Depends(get_db)) -> list[DocumentVersionOut]:
    rows = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.contract_id == contract_id)
        .order_by(DocumentVersion.version_number)
        .all()
    )
    return [DocumentVersionOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/version/{version_id}/download")
def download_version(version_id: str, db: Session = Depends(get_db)) -> FileResponse:
    row = db.get(DocumentVersion, version_id)
    if row is None:
        raise HTTPException(404, f"document version {version_id!r} not found")
    path = Path(row.file_path)
    if not path.exists():
        raise HTTPException(404, f"file for version {version_id!r} is missing on disk")
    return FileResponse(
        path,
        filename=f"{row.contract_id}_v{row.version_number}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
