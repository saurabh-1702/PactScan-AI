"""The Restore Executor — the only code permitted to write a file for a
Document Restore (Phase 6's analogue of Phase 3's Fix & Learn Executor).

Called from exactly one place: ``POST /api/restore-requests/{id}/decide`` on
an "approved" decision. Never call this function from anywhere else — same
one-entry-point rule as ``app/agents/fix_and_learn/executor.py``.

Unlike a redline approval, restoring never edits text — it just copies the
target version's file forward as a brand-new version, so the full version
history is never shortened: restoring to v2 when the contract is at v5
produces a NEW v6 (a copy of v2's content), leaving v2-v5 exactly as they
were.
"""

from __future__ import annotations

import json
import shutil

from sqlalchemy.orm import Session

from app.agents.detect.graph_store import DEMO_TENANT
from app.agents.fix_and_learn.document_store import get_contract_dir
from app.db.models import AuditLog, DocumentVersion, RestoreRequest


class RestoreNotAuthorizedError(Exception):
    """Raised if this is ever called on a request that isn't 'approved' —
    should be unreachable given the API route's own guard; defense in depth,
    mirroring ExecutorNotAuthorizedError in fix_and_learn/executor.py."""


def apply_approved_restore(
    db: Session, restore_request_id: str, tenant_id: str = DEMO_TENANT
) -> DocumentVersion:
    request = db.get(RestoreRequest, restore_request_id)
    if request is None:
        raise ValueError(f"RestoreRequest {restore_request_id!r} not found.")
    if request.status != "approved":
        raise RestoreNotAuthorizedError(
            f"RestoreRequest {restore_request_id!r} is not approved (status={request.status!r})."
        )

    target = db.get(DocumentVersion, request.target_version_id)
    if target is None:
        raise ValueError(f"Target document version {request.target_version_id!r} not found.")

    latest = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.contract_id == request.contract_id)
        .order_by(DocumentVersion.version_number.desc())
        .first()
    )
    if latest is None:
        raise RuntimeError(
            f"No document_versions entry exists for contract {request.contract_id!r}."
        )

    new_version_number = latest.version_number + 1
    contract_dir = get_contract_dir(tenant_id, request.contract_id)
    new_path = contract_dir / f"v{new_version_number}.docx"

    # no text edit at all — just copy the target version's bytes forward
    shutil.copy2(target.file_path, new_path)

    new_version = DocumentVersion(
        tenant_id=tenant_id,
        contract_id=request.contract_id,
        version_number=new_version_number,
        file_path=str(new_path),
        approval_id=None,  # this version came from a RestoreRequest, not an Approval
    )
    db.add(new_version)
    db.add(
        AuditLog(
            event_type="document_restored",
            entity_id=request.contract_id,
            details=json.dumps(
                {
                    "restore_request_id": request.id,
                    "target_version_id": target.id,
                    "target_version_number": target.version_number,
                    "new_version": new_version_number,
                }
            ),
        )
    )
    db.commit()
    db.refresh(new_version)
    return new_version
