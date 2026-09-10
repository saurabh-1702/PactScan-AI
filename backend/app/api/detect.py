"""Detect agent API.

POST /api/detect            -> upload a contract, run the full pipeline
GET  /api/detect/{id}      -> return previously-computed findings (no re-run)
"""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.agents.detect.graph_store import GraphStore, get_graph_store
from app.agents.detect.pipeline import get_report, ingest_and_detect
from app.models.clause import DetectReport

logger = logging.getLogger("pactscan.api.detect")

router = APIRouter(prefix="/api/detect", tags=["detect"])

_ALLOWED_SUFFIXES = {".pdf", ".docx", ".doc", ".txt"}


def get_store() -> GraphStore:
    return get_graph_store()


@router.post("", response_model=DetectReport)
@router.post("/", response_model=DetectReport, include_in_schema=False)
async def detect(
    file: UploadFile = File(...),
    store: GraphStore = Depends(get_store),
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
        report = await ingest_and_detect(store, tmp_path, filename)
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
) -> DetectReport:
    report = get_report(store, contract_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"Contract {contract_id!r} not found.")
    return report
