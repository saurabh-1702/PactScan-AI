"""Approval queue API — the human-in-the-loop gate.

POST /api/approvals              -> create a pending approval for a suggestion
                                     (normally auto-created by Suggest itself;
                                     this exists for manual/standalone re-queuing)
GET  /api/approvals?status=...   -> list approvals (with the suggestion inlined)
POST /api/approvals/{id}/decide  -> approve or reject

    THIS IS THE ONLY ENTRY POINT INTO THE EXECUTOR.
    DO NOT CALL THE EXECUTOR (app.agents.fix_and_learn.executor) DIRECTLY
    FROM ANYWHERE ELSE IN THE CODEBASE. Every write to a real document must be
    traceable to exactly one logged, decided Approval row.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.agents.detect.graph_store import GraphStore, get_graph_store
from app.agents.fix_and_learn.executor import (
    ExecutorClauseNotFoundError,
    ExecutorNotAuthorizedError,
    apply_approved_redline,
)
from app.agents.fix_and_learn.playbook_feedback import record_accepted_redline
from app.api.deps import CurrentUser, get_current_user, require_role
from app.db.models import Approval, AuditLog, RedlineSuggestion
from app.db.postgres_client import get_db
from app.models.approval import ApprovalOut, CreateApprovalRequest, DecideRequest

logger = logging.getLogger("pactscan.api.approvals")

router = APIRouter(prefix="/api/approvals", tags=["approvals"])


def get_store() -> GraphStore:
    return get_graph_store()


def _to_out(
    approval: Approval, suggestion: RedlineSuggestion, store: GraphStore, tenant_id: str
) -> ApprovalOut:
    clause = store.get_clause_by_id(suggestion.clause_id, tenant_id=tenant_id)
    return ApprovalOut(
        id=approval.id,
        redline_suggestion_id=approval.redline_suggestion_id,
        status=approval.status,
        reviewer_note=approval.reviewer_note,
        edited_text=approval.edited_text,
        decided_at=approval.decided_at,
        created_at=approval.created_at,
        finding_id=suggestion.finding_id,
        contract_id=suggestion.contract_id,
        clause_id=suggestion.clause_id,
        original_clause_text=clause.raw_text if clause else "(clause not found in graph)",
        proposed_text=suggestion.proposed_text,
        rationale=suggestion.rationale,
        confidence=suggestion.confidence,
    )


@router.post("", response_model=ApprovalOut)
def create_approval(
    body: CreateApprovalRequest,
    db: Session = Depends(get_db),
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
) -> ApprovalOut:
    suggestion = db.get(RedlineSuggestion, body.redline_suggestion_id)
    if suggestion is None or suggestion.tenant_id != current_user.tenant_id:
        raise HTTPException(404, f"redline_suggestion {body.redline_suggestion_id!r} not found")

    approval = Approval(redline_suggestion_id=suggestion.id, status="pending")
    db.add(approval)
    db.flush()  # assigns approval.id before it's referenced below
    db.add(
        AuditLog(
            event_type="approval_created",
            entity_id=approval.id,
            details=json.dumps({"redline_suggestion_id": suggestion.id}),
        )
    )
    db.commit()
    db.refresh(approval)
    return _to_out(approval, suggestion, store, current_user.tenant_id)


@router.get("", response_model=list[ApprovalOut])
def list_approvals(
    status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ApprovalOut]:
    q = (
        db.query(Approval)
        .join(RedlineSuggestion, Approval.redline_suggestion_id == RedlineSuggestion.id)
        .filter(RedlineSuggestion.tenant_id == current_user.tenant_id)
    )
    if status:
        q = q.filter(Approval.status == status)
    rows = q.order_by(Approval.created_at).all()

    out: list[ApprovalOut] = []
    for approval in rows:
        suggestion = db.get(RedlineSuggestion, approval.redline_suggestion_id)
        if suggestion is None:
            continue  # orphaned row; shouldn't happen, skip defensively
        out.append(_to_out(approval, suggestion, store, current_user.tenant_id))
    return out


@router.post("/{approval_id}/decide", response_model=ApprovalOut)
def decide_approval(
    approval_id: str,
    body: DecideRequest,
    db: Session = Depends(get_db),
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(require_role(["reviewer", "admin"])),
) -> ApprovalOut:
    # ---------------------------------------------------------------------
    # THIS IS THE ONLY ENTRY POINT INTO THE EXECUTOR.
    # DO NOT CALL THE EXECUTOR DIRECTLY FROM ANYWHERE ELSE.
    # ---------------------------------------------------------------------
    approval = db.get(Approval, approval_id)
    if approval is None:
        raise HTTPException(404, f"approval {approval_id!r} not found")

    suggestion = db.get(RedlineSuggestion, approval.redline_suggestion_id)
    if suggestion is None or suggestion.tenant_id != current_user.tenant_id:
        raise HTTPException(404, f"approval {approval_id!r} not found")
    if approval.status != "pending":
        raise HTTPException(409, f"approval {approval_id!r} was already decided ({approval.status})")

    approval.status = body.decision
    approval.reviewer_note = body.note
    approval.edited_text = body.edited_text
    approval.decided_at = datetime.now(timezone.utc)
    db.add(
        AuditLog(
            event_type="approval_decided",
            entity_id=approval.id,
            details=json.dumps(
                {"decision": body.decision, "note": body.note, "edited": bool(body.edited_text)}
            ),
        )
    )
    db.commit()
    db.refresh(approval)

    if body.decision == "rejected":
        return _to_out(approval, suggestion, store, current_user.tenant_id)

    # approved -> call the Executor (and only the Executor, and only here)
    try:
        apply_approved_redline(db, store, approval.id, tenant_id=current_user.tenant_id)
    except ExecutorNotAuthorizedError as exc:
        # should be unreachable given the pending-check above; fail loudly if it ever happens
        logger.error("Executor authorization guard tripped unexpectedly: %s", exc)
        raise HTTPException(500, str(exc)) from exc
    except ExecutorClauseNotFoundError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(422, str(exc)) from exc

    clause = store.get_clause_by_id(suggestion.clause_id, tenant_id=current_user.tenant_id)
    if clause is not None:
        record_accepted_redline(
            db,
            clause_type=clause.clause_type.value,
            accepted_text=approval.edited_text or suggestion.proposed_text,
        )

    db.refresh(approval)
    return _to_out(approval, suggestion, store, current_user.tenant_id)
