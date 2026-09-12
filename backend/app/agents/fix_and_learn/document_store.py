"""Local filesystem document storage + version-1 capture (Phase 3).

Storage layout: ``backend\\storage\\documents\\{tenant_id}\\{contract_id}\\v{N}.docx``

**Design note — why a synthesized .docx, not the raw upload, for PDF sources:**
python-docx can only edit `.docx` files, but Detect accepts PDF/DOC/DOCX/TXT
uploads (via LlamaParse). If the original upload is already a `.docx`, it is
stored byte-for-byte as version 1. If it isn't (our own test fixtures are
PDFs, and this is the common real-world case too), a `.docx` is *synthesized*
from Detect's own structured clause extraction — one paragraph per clause, in
page order — and that becomes version 1 instead. This guarantees the
Executor's exact-text clause matching works against the same `raw_text`
Detect/Suggest already reasoned about.

This is an explicit, documented simplification for this build (see
docs/SETUP_NOTES.md) — a production system would need real PDF-to-Word
conversion, or to require Word-native uploads for anything headed toward an
approval-gated write.
"""

from __future__ import annotations

import io
import logging
from pathlib import Path

from docx import Document
from sqlalchemy.orm import Session

from app.db.models import DocumentVersion
from app.models.clause import ExtractedClause

logger = logging.getLogger("pactscan.fix_and_learn.document_store")

STORAGE_ROOT = Path(__file__).resolve().parents[3] / "storage" / "documents"


def get_contract_dir(tenant_id: str, contract_id: str) -> Path:
    d = STORAGE_ROOT / tenant_id / contract_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def synthesize_docx_bytes(clauses: list[ExtractedClause]) -> bytes:
    """Build a .docx reconstruction of a contract from its extracted clauses."""
    doc = Document()
    doc.add_heading("Reconstructed Contract (synthesized from extracted clauses)", level=1)
    doc.add_paragraph(
        "This document was reconstructed from structured clause extraction because "
        "the original upload was not a Word document. See docs/SETUP_NOTES.md."
    )
    for clause in sorted(clauses, key=lambda c: (c.page_number, c.clause_id)):
        doc.add_heading(f"Page {clause.page_number} — {clause.section_header}", level=2)
        doc.add_paragraph(clause.raw_text)

    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def ensure_initial_version(
    db: Session,
    tenant_id: str,
    contract_id: str,
    filename: str,
    raw_bytes: bytes,
    clauses: list[ExtractedClause],
) -> DocumentVersion | None:
    """Capture version 1 for a contract, if it doesn't already have one.
    Idempotent: returns None (no-op) if a version already exists."""
    existing = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.contract_id == contract_id)
        .first()
    )
    if existing is not None:
        return None

    is_docx = filename.lower().endswith(".docx")
    content = raw_bytes if is_docx else synthesize_docx_bytes(clauses)

    path = get_contract_dir(tenant_id, contract_id) / "v1.docx"
    path.write_bytes(content)

    version = DocumentVersion(
        contract_id=contract_id,
        version_number=1,
        file_path=str(path),
        approval_id=None,
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    logger.info(
        "Captured version 1 for contract %s (%s)",
        contract_id,
        "original .docx" if is_docx else "synthesized from clauses",
    )
    return version
