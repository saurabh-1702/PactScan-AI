"""Detect agent API.

POST /api/detect            -> upload a contract, run the full pipeline
GET  /api/detect/{id}      -> return previously-computed findings (no re-run)
"""

from __future__ import annotations

import logging
import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.agents.detect.graph_store import GraphStore, get_graph_store
from app.agents.detect.pipeline import get_report, ingest_and_detect
from app.api.access import ensure_contract_access
from app.api.deps import CurrentUser, get_current_user
from app.core.progress import JobProgress
from app.db.postgres_client import get_db
from app.models.clause import DetectReport

logger = logging.getLogger("pactscan.api.detect")

router = APIRouter(prefix="/api/detect", tags=["detect"])

_ALLOWED_SUFFIXES = {".pdf", ".docx", ".doc", ".txt"}


def get_store() -> GraphStore:
    return get_graph_store()


_JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{8,64}$")


def _valid_job_id(job_id: str | None) -> str | None:
    """A client-chosen id for progress polling; ignored unless well-formed."""
    return job_id if job_id and _JOB_ID_RE.match(job_id) else None


@router.post("", response_model=DetectReport)
@router.post("/", response_model=DetectReport, include_in_schema=False)
async def detect(
    file: UploadFile = File(...),
    job_id: str | None = Form(default=None),
    store: GraphStore = Depends(get_store),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DetectReport:
    filename = file.filename or "contract.pdf"
    suffix = Path(filename).suffix.lower()
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type {suffix!r}. Allowed: {sorted(_ALLOWED_SUFFIXES)}",
        )

    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    tmp_dir = Path(tempfile.mkdtemp(prefix="pactscan_detect_"))
    tmp_path = tmp_dir / filename
    tmp_path.write_bytes(data)
    try:
        report = await ingest_and_detect(
            store,
            tmp_path,
            filename,
            tenant_id=current_user.tenant_id,
            db=db,
            uploaded_by_user_id=current_user.user_id,
            progress=JobProgress.begin(
                _valid_job_id(job_id), current_user.user_id, current_user.tenant_id, f"Scanning {filename}"
            ),
        )
    except RuntimeError as exc:
        logger.exception("Detect pipeline failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    finally:
        try:
            tmp_path.unlink(missing_ok=True)
            tmp_dir.rmdir()
        except OSError:
            pass

    return report


@router.get("/{contract_id}", response_model=DetectReport)
async def get_detect(
    contract_id: str,
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
) -> DetectReport:
    ensure_contract_access(store, current_user, contract_id)
    report = get_report(store, contract_id, tenant_id=current_user.tenant_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Contract {contract_id!r} not found.")
    return report
