"""The Executor — the only code in this entire project permitted to write an
approved redline into a real document.

Called from exactly one place: ``POST /api/approvals/{id}/decide`` on an
"approved" decision. Never call this function from anywhere else.

Every write:
  1. re-verifies the approval's status from the database (defense in depth —
     the API route already checks this, but the guard lives here too)
  2. never edits a file in place — copies the current version's bytes to a new
     path first, then edits the copy
  3. applies a *visual* tracked-changes style, not Word's native revision XML
     (python-docx doesn't support that well) — struck-through red text for the
     original clause, underlined green text for the replacement
  4. registers the result as a new document_versions row; the prior version's
     row and file are never touched (this is what makes Phase 6's restore
     possible)
  5. writes an audit_log row
"""

from __future__ import annotations

import json
import logging
import shutil
from datetime import datetime, timezone

from docx import Document
from docx.shared import RGBColor
from sqlalchemy.orm import Session

from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.agents.fix_and_learn.document_store import get_contract_dir
from app.db.models import Approval, AuditLog, DocumentVersion, RedlineSuggestion

logger = logging.getLogger("pactscan.fix_and_learn.executor")

_STRIKE_COLOR = RGBColor(0xC0, 0x00, 0x00)  # red
_INSERT_COLOR = RGBColor(0x00, 0x66, 0x00)  # green


class ExecutorNotAuthorizedError(Exception):
    """Raised if the Executor is invoked for an approval that is not
    (or no longer) in the 'approved' state. Must never be bypassed."""


class ExecutorClauseNotFoundError(Exception):
    """Raised if the target clause text cannot be located in the current
    document version — never silently skipped."""


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _apply_tracked_change(doc: Document, original_text: str, new_text: str) -> bool:
    """Find the paragraph matching ``original_text`` and replace its runs with
    a visual strike-through (old) + underline (new) pair. Returns True if a
    match was found and edited."""
    target = _normalize(original_text)
    for paragraph in doc.paragraphs:
        candidate = _normalize(paragraph.text)
        if candidate == target or (target and target in candidate):
            for run in list(paragraph.runs):
                run.text = ""
            old_run = paragraph.add_run(original_text)
            old_run.font.strike = True
            old_run.font.color.rgb = _STRIKE_COLOR

            paragraph.add_run("  →  ")  # visual separator

            new_run = paragraph.add_run(new_text)
            new_run.font.underline = True
            new_run.font.color.rgb = _INSERT_COLOR
            return True
    return False


def apply_approved_redline(
    db: Session,
    store: GraphStore,
    approval_id: str,
    tenant_id: str = DEMO_TENANT,
) -> DocumentVersion:
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise ValueError(f"Approval {approval_id!r} not found.")

    # --- guard clause: defense in depth, even though the API route already checks this ---
    if approval.status != "approved":
        raise ExecutorNotAuthorizedError(
            f"Approval {approval_id!r} is not approved (status={approval.status!r}). "
            "The Executor must never write without a logged 'approved' decision."
        )

    suggestion = db.get(RedlineSuggestion, approval.redline_suggestion_id)
    if suggestion is None:
        raise ValueError(f"RedlineSuggestion {approval.redline_suggestion_id!r} not found.")

    clause = store.get_clause_by_id(suggestion.clause_id, tenant_id=tenant_id)
    if clause is None:
        raise ValueError(f"Clause {suggestion.clause_id!r} not found in the graph.")

    latest = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.contract_id == suggestion.contract_id)
        .order_by(DocumentVersion.version_number.desc())
        .first()
    )
    if latest is None:
        raise RuntimeError(
            f"No document_versions entry exists for contract {suggestion.contract_id!r} — "
            "the original document was never captured (see document_store.ensure_initial_version)."
        )

    proposed_text = approval.edited_text or suggestion.submitted_text

    contract_dir = get_contract_dir(tenant_id, suggestion.contract_id)
    new_version_number = latest.version_number + 1
    new_path = contract_dir / f"v{new_version_number}.docx"

    # never edit the current file in place — copy first, then edit the copy
    shutil.copy2(latest.file_path, new_path)

    doc = Document(str(new_path))
    found = _apply_tracked_change(doc, clause.raw_text, proposed_text)
    if not found:
        new_path.unlink(missing_ok=True)
        raise ExecutorClauseNotFoundError(
            f"Could not locate clause {clause.clause_id!r}'s text in "
            f"{latest.file_path!r} — no edit was made."
        )
    doc.save(str(new_path))

    new_version = DocumentVersion(
        tenant_id=tenant_id,
        contract_id=suggestion.contract_id,
        version_number=new_version_number,
        file_path=str(new_path),
        approval_id=approval.id,
    )
    db.add(new_version)
    db.add(
        AuditLog(
            event_type="document_written",
            entity_id=suggestion.contract_id,
            details=json.dumps(
                {
                    "approval_id": approval.id,
                    "redline_suggestion_id": suggestion.id,
                    "clause_id": clause.clause_id,
                    "old_file_path": latest.file_path,
                    "new_file_path": str(new_path),
                    "old_version": latest.version_number,
                    "new_version": new_version_number,
                }
            ),
        )
    )
    db.commit()
    db.refresh(new_version)
    logger.info(
        "Executor wrote contract %s version %d (approval %s)",
        suggestion.contract_id,
        new_version_number,
        approval.id,
    )
    return new_version
