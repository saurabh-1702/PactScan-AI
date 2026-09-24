"""Document Restore API (Phase 6).

POST /api/restore-requests              -> any role may request a restore
                                            (never writes a file — see
                                            restore_agent.py)
GET  /api/restore-requests?status=...   -> list this tenant's requests
POST /api/restore-requests/{id}/decide  -> reviewer/admin only.

    THIS IS THE ONLY ENTRY POINT INTO THE RESTORE EXECUTOR.
    DO NOT CALL app.agents.restore.executor DIRECTLY FROM ANYWHERE ELSE.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agents.notifications.notify import notify_restore_decision
from app.agents.restore.executor import RestoreNotAuthorizedError, apply_approved_restore
from app.agents.restore.restore_agent import RestoreInputError, create_restore_request
from app.agents.detect.graph_store import GraphStore, get_graph_store
from app.api.access import ensure_contract_access, visible_contract_ids
from app.api.deps import CurrentUser, get_current_user, require_role
from app.db.models import DocumentVersion, RestoreRequest, User
from app.db.postgres_client import get_db
from app.models.restore import CreateRestoreRequest, DecideRestoreRequest, RestoreRequestOut

logger = logging.getLogger("pactscan.api.restore_requests")

router = APIRouter(prefix="/api/restore-requests", tags=["restore"])


def get_store() -> GraphStore:
    return get_graph_store()


def _to_out(request: RestoreRequest, db: Session) -> RestoreRequestOut:
    target = db.get(DocumentVersion, request.target_version_id)
    requester = db.get(User, request.requested_by_user_id)
    decider = db.get(User, request.decided_by_user_id) if request.decided_by_user_id else None
    return RestoreRequestOut(
        id=request.id,
        contract_id=request.contract_id,
        target_version_id=request.target_version_id,
        target_version_number=target.version_number if target else -1,
        requested_by_user_id=request.requested_by_user_id,
        requested_by_email=requester.email if requester else None,
        reason=request.reason,
        status=request.status,
        reviewer_note=request.reviewer_note,
        abuse_flagged=request.abuse_flagged,
        decided_at=request.decided_at,
        decided_by_email=decider.email if decider else None,
        created_at=request.created_at,
    )


@router.post("", response_model=RestoreRequestOut)
def create_request(
    body: CreateRestoreRequest,
    db: Session = Depends(get_db),
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
) -> RestoreRequestOut:
    ensure_contract_access(store, current_user, body.contract_id)
    try:
        request = create_restore_request(
            db,
            body.contract_id,
            body.target_version_id,
            current_user.user_id,
            body.reason,
            tenant_id=current_user.tenant_id,
        )
    except RestoreInputError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _to_out(request, db)


@router.get("", response_model=list[RestoreRequestOut])
def list_requests(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[RestoreRequestOut]:
    q = db.query(RestoreRequest).filter(RestoreRequest.tenant_id == current_user.tenant_id)
    visible = visible_contract_ids(store, current_user)
    if visible is not None:
        q = q.filter(RestoreRequest.contract_id.in_(visible))
    if status:
        q = q.filter(RestoreRequest.status == status)
    rows = q.order_by(RestoreRequest.created_at).all()
    return [_to_out(r, db) for r in rows]


@router.post("/{request_id}/decide", response_model=RestoreRequestOut)
def decide_request(
    request_id: str,
    body: DecideRestoreRequest,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(["reviewer", "admin"])),
) -> RestoreRequestOut:
    # ---------------------------------------------------------------------
    # THIS IS THE ONLY ENTRY POINT INTO THE RESTORE EXECUTOR.
    # ---------------------------------------------------------------------
    request = db.get(RestoreRequest, request_id)
    if request is None or request.tenant_id != current_user.tenant_id:
        raise HTTPException(404, f"restore request {request_id!r} not found")
    if request.status != "pending":
        raise HTTPException(409, f"restore request {request_id!r} was already decided ({request.status})")

    request.status = body.decision
    request.reviewer_note = body.note
    request.decided_by_user_id = current_user.user_id
    request.decided_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(request)

    if body.decision == "rejected":
        notify_restore_decision(
            db, request, "rejected", body.note, None, decided_by_user_id=current_user.user_id
        )
        return _to_out(request, db)

    try:
        new_version = apply_approved_restore(db, request.id, tenant_id=current_user.tenant_id)
    except RestoreNotAuthorizedError as exc:
        logger.error("Restore authorization guard tripped unexpectedly: %s", exc)
        raise HTTPException(500, str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc

    notify_restore_decision(
        db, request, "approved", body.note, new_version.id, decided_by_user_id=current_user.user_id
    )

    db.refresh(request)
    return _to_out(request, db)
