"""A requester's own drafts (Phase 6b).

GET  /api/my-drafts                 -> every suggestion the caller requested,
                                        newest first, with its status
GET  /api/my-drafts/{id}            -> one of them
POST /api/my-drafts/{id}/submit     -> put a DRAFT in front of a reviewer,
                                        optionally with the requester's own edit

Suggest and Ask's edit instructions only DRAFT; nothing reaches the reviewer's
queue until the requester submits it here. Submitting is the only thing this
router can do to the approval queue — it never decides anything and never
touches the Executor.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.detect.graph_store import GraphStore, get_graph_store
from app.agents.suggest.pipeline import SubmissionError, enqueue_for_review
from app.api.access import ensure_contract_access
from app.api.deps import CurrentUser, get_current_user
from app.db.models import Approval, DocumentVersion, RedlineSuggestion
from app.db.postgres_client import get_db
from app.models.drafts import DraftOut, SubmitDraftRequest

router = APIRouter(prefix="/api/my-drafts", tags=["my-drafts"])


def get_store() -> GraphStore:
    return get_graph_store()


def _build(db: Session, store: GraphStore, sg: RedlineSuggestion, filenames: dict[str, str]) -> DraftOut:
    approval = (
        db.query(Approval)
        .filter(Approval.redline_suggestion_id == sg.id)
        .order_by(Approval.created_at.desc())
        .first()
    )
    clause = store.get_clause_by_id(sg.clause_id, tenant_id=sg.tenant_id)
    version = None
    if approval is not None and approval.status == "approved":
        version = db.query(DocumentVersion).filter(DocumentVersion.approval_id == approval.id).first()
    return DraftOut(
        suggestion_id=sg.id,
        contract_id=sg.contract_id,
        filename=filenames.get(sg.contract_id),
        clause_id=sg.clause_id,
        finding_id=sg.finding_id,
        original_clause_text=clause.raw_text if clause else "(clause not found in graph)",
        ai_draft_text=sg.proposed_text,
        requester_edited_text=sg.requester_edited_text,
        rationale=sg.rationale,
        confidence=sg.confidence,
        status="draft" if approval is None else approval.status,
        approval_id=approval.id if approval else None,
        reviewer_edited_text=approval.edited_text if approval else None,
        reviewer_note=approval.reviewer_note if approval else None,
        document_version_id=version.id if version else None,
        created_at=sg.created_at,
        submitted_at=approval.created_at if approval else None,
        decided_at=approval.decided_at if approval else None,
    )


def _filenames(store: GraphStore, tenant_id: str) -> dict[str, str]:
    return {c["contract_id"]: c["filename"] for c in store.list_contracts(tenant_id=tenant_id)}


def _own_suggestion(db: Session, suggestion_id: str, user: CurrentUser) -> RedlineSuggestion:
    sg = db.get(RedlineSuggestion, suggestion_id)
    # 404 rather than 403 for someone else's draft — don't reveal it exists
    if sg is None or sg.tenant_id != user.tenant_id or sg.requested_by_user_id != user.user_id:
        raise HTTPException(404, f"draft {suggestion_id!r} not found")
    return sg


@router.get("", response_model=list[DraftOut])
def list_my_drafts(
    db: Session = Depends(get_db),
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[DraftOut]:
    rows = (
        db.query(RedlineSuggestion)
        .filter(
            RedlineSuggestion.tenant_id == current_user.tenant_id,
            RedlineSuggestion.requested_by_user_id == current_user.user_id,
        )
        .order_by(RedlineSuggestion.created_at.desc())
        .all()
    )
    filenames = _filenames(store, current_user.tenant_id)
    return [_build(db, store, sg, filenames) for sg in rows]


@router.get("/{suggestion_id}", response_model=DraftOut)
def get_my_draft(
    suggestion_id: str,
    db: Session = Depends(get_db),
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
) -> DraftOut:
    sg = _own_suggestion(db, suggestion_id, current_user)
    return _build(db, store, sg, _filenames(store, current_user.tenant_id))


@router.post("/{suggestion_id}/submit", response_model=DraftOut)
def submit_draft(
    suggestion_id: str,
    body: SubmitDraftRequest,
    db: Session = Depends(get_db),
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
) -> DraftOut:
    sg = _own_suggestion(db, suggestion_id, current_user)
    ensure_contract_access(store, current_user, sg.contract_id)
    try:
        enqueue_for_review(db, sg, body.edited_text, source="requester_submit")
    except SubmissionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    db.refresh(sg)
    return _build(db, store, sg, _filenames(store, current_user.tenant_id))
