"""Document Restore — request flow (Phase 6).

Only ever creates a pending row here — never writes to a file. Writing
happens exactly once, in ``executor.py::apply_approved_restore``, and only
after a reviewer/admin decides ``approved`` via
POST /api/restore-requests/{id}/decide — the same human-approval gate every
other document write in this project goes through.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.detect.graph_store import DEMO_TENANT
from app.agents.restore.abuse_check import check_and_flag_restore_abuse
from app.db.models import DocumentVersion, RestoreRequest


class RestoreInputError(ValueError):
    """A user-facing 4xx-shaped error (empty reason, unknown version, etc.)."""


def create_restore_request(
    db: Session,
    contract_id: str,
    target_version_id: str,
    requested_by_user_id: str,
    reason: str,
    tenant_id: str = DEMO_TENANT,
) -> RestoreRequest:
    reason = reason.strip()
    if not reason:
        raise RestoreInputError("A reason is required to request a restore.")

    target = db.get(DocumentVersion, target_version_id)
    if target is None or target.tenant_id != tenant_id or target.contract_id != contract_id:
        raise RestoreInputError(f"Document version {target_version_id!r} not found.")

    request = RestoreRequest(
        tenant_id=tenant_id,
        contract_id=contract_id,
        target_version_id=target_version_id,
        requested_by_user_id=requested_by_user_id,
        reason=reason,
        status="pending",
    )
    db.add(request)
    db.commit()
    db.refresh(request)

    check_and_flag_restore_abuse(db, contract_id, request.id)
    db.refresh(request)
    return request
