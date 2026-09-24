"""End-to-end Detect pipeline: file -> parse -> extract -> graph -> findings."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from app.agents.detect import graph_writer, ingest
from app.agents.detect.detect_agent import run_detect
from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.core.progress import JobProgress
from app.models.clause import DetectReport

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger("pactscan.detect.pipeline")


async def ingest_and_detect(
    store: GraphStore,
    file_path: str | Path,
    filename: str,
    tenant_id: str = DEMO_TENANT,
    contract_id: str | None = None,
    db: "Session | None" = None,
    uploaded_by_user_id: str | None = None,
    progress: JobProgress | None = None,
) -> DetectReport:
    """``db`` is optional (Phase 3) — when provided, the original upload (or a
    synthesized .docx reconstruction, if it wasn't already a .docx) is
    captured as document_versions version 1. Omitting it preserves exact
    Phase 1/2 behaviour for existing callers/tests."""
    progress = progress or JobProgress()
    try:
        return await _run(
            store, file_path, filename, tenant_id, contract_id, db, uploaded_by_user_id, progress
        )
    except Exception as exc:
        progress.fail(str(exc) or exc.__class__.__name__)
        raise


async def _run(
    store: GraphStore,
    file_path: str | Path,
    filename: str,
    tenant_id: str,
    contract_id: str | None,
    db: "Session | None",
    uploaded_by_user_id: str | None,
    progress: JobProgress,
) -> DetectReport:
    contract_id = contract_id or f"ct_{uuid.uuid4().hex[:12]}"

    progress.advance("parse")
    parsed = ingest.parse_document(file_path)
    progress.advance("extract")
    clauses = await ingest.extract_clauses(parsed, contract_id)
    progress.advance("graph")
    await graph_writer.write_contract_graph(
        store,
        contract_id,
        filename,
        clauses,
        tenant_id=tenant_id,
        uploaded_by_user_id=uploaded_by_user_id,
    )
    progress.advance("check")
    findings = await run_detect(store, contract_id, tenant_id=tenant_id)

    progress.advance("save")
    if db is not None:
        from app.agents.fix_and_learn.document_store import ensure_initial_version
        from app.agents.notifications.notify import notify_new_findings

        stored_clauses = store.get_clauses_for_contract(contract_id, tenant_id=tenant_id)
        ensure_initial_version(
            db, tenant_id, contract_id, filename, Path(file_path).read_bytes(), stored_clauses
        )
        notify_new_findings(
            db, tenant_id, filename, findings, contract_owner_user_id=uploaded_by_user_id
        )

    progress.finish()
    return DetectReport(
        contract_id=contract_id,
        filename=filename,
        findings=findings,
        total_findings=len(findings),
        timestamp=_detect_timestamp(store, contract_id, tenant_id),
    )


def get_report(
    store: GraphStore, contract_id: str, tenant_id: str = DEMO_TENANT
) -> DetectReport | None:
    if not store.contract_exists(contract_id, tenant_id=tenant_id):
        return None
    findings = store.get_findings(contract_id, tenant_id=tenant_id)
    filename = _filename(store, contract_id, tenant_id)
    return DetectReport(
        contract_id=contract_id,
        filename=filename,
        findings=findings,
        total_findings=len(findings),
        timestamp=_detect_timestamp(store, contract_id, tenant_id),
    )


def _detect_timestamp(store: GraphStore, contract_id: str, tenant_id: str):
    from datetime import datetime

    ts = store.get_detect_run(contract_id, tenant_id=tenant_id)
    return datetime.fromisoformat(ts) if ts else None


def _filename(store: GraphStore, contract_id: str, tenant_id: str) -> str:
    # in-memory store keeps the contract dict; Neo4j store can look it up
    from app.agents.detect.graph_store import InMemoryGraphStore, Neo4jGraphStore

    if isinstance(store, InMemoryGraphStore):
        rec = store.contracts.get((tenant_id, contract_id))
        return rec["filename"] if rec else contract_id
    if isinstance(store, Neo4jGraphStore):
        rows = store._run(
            "MATCH (c:Contract {id: $id, tenant_id: $t}) RETURN c.filename AS fn",
            id=contract_id,
            t=tenant_id,
        )
        return rows[0]["fn"] if rows and rows[0].get("fn") else contract_id
    return contract_id
