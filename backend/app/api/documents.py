"""Document version listing + download (Phase 3).

Read-only. Writing a new version only ever happens via the Executor, triggered
from POST /api/approvals/{id}/decide.
"""

from __future__ import annotations

from pathlib import Path

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.agents.detect.graph_store import GraphStore, get_graph_store
from app.agents.fix_and_learn.clean_copy import make_clean_docx
from app.api.access import ensure_contract_access
from app.api.deps import CurrentUser, get_current_user
from app.db.models import DocumentVersion
from app.db.postgres_client import get_db
from app.models.approval import DocumentVersionOut

router = APIRouter(prefix="/api/documents", tags=["documents"])


def get_store() -> GraphStore:
    return get_graph_store()


@router.get("/contract/{contract_id}/versions", response_model=list[DocumentVersionOut])
def list_versions(
    contract_id: str,
    db: Session = Depends(get_db),
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[DocumentVersionOut]:
    ensure_contract_access(store, current_user, contract_id)
    rows = (
        db.query(DocumentVersion)
        .filter(
            DocumentVersion.contract_id == contract_id,
            DocumentVersion.tenant_id == current_user.tenant_id,
        )
        .order_by(DocumentVersion.version_number)
        .all()
    )
    return [DocumentVersionOut.model_validate(r, from_attributes=True) for r in rows]


@router.get("/version/{version_id}/download")
def download_version(
    version_id: str,
    format: Literal["redline", "clean"] = Query(
        default="redline",
        description="redline = changes marked (strike-through / underline); clean = changes accepted",
    ),
    db: Session = Depends(get_db),
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
) -> FileResponse:
    row = db.get(DocumentVersion, version_id)
    # 404, not 403, on a tenant mismatch — don't reveal that the id exists at all
    if row is None or row.tenant_id != current_user.tenant_id:
        raise HTTPException(404, f"document version {version_id!r} not found")
    ensure_contract_access(store, current_user, row.contract_id)
    path = Path(row.file_path)
    if not path.exists():
        raise HTTPException(404, f"file for version {version_id!r} is missing on disk")
    media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if format == "clean":
        # generated on the fly from the stored version — nothing new is stored
        return Response(
            content=make_clean_docx(path.read_bytes()),
            media_type=media_type,
            headers={
                "Content-Disposition": f'attachment; filename="{row.contract_id}_v{row.version_number}_clean.docx"'
            },
        )
    return FileResponse(
        path,
        filename=f"{row.contract_id}_v{row.version_number}.docx",
        media_type=media_type,
    )
