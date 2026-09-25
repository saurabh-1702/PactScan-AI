"""Suggest agent — end-to-end orchestration.

    Retriever -> draft -> Contrarian -> Judge -> Negotiation Twin -> persist

Two entry points, both standalone-capable per the architecture requirement:
  * ``suggest_from_finding`` — chained from a Phase 1 Detect finding
  * ``suggest_standalone``   — a manually-specified clause + free-text request,
    with no prior finding at all

Never writes to a file. Every result is persisted to Postgres (``redline_suggestions``)
and returned; the human-approval write path is Phase 3.
"""

from __future__ import annotations

import json
import logging

from sqlalchemy.orm import Session

from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.agents.suggest.adversarial_review import run_contrarian, run_judge
from app.agents.suggest.draft_redline import draft_redline
from app.agents.suggest.negotiation_twin import run_negotiation_twin
from app.agents.suggest.retriever import retrieve_context
from app.db.models import Approval, AuditLog, RedlineSuggestion
from app.models.clause import ExtractedClause
from app.models.redline import RetrievedContext, SuggestResult

logger = logging.getLogger("pactscan.suggest.pipeline")


class SuggestInputError(ValueError):
    """A user-facing 4xx-shaped error (unknown finding/clause, mismatch, etc.)."""


async def suggest_from_finding(
    store: GraphStore,
    db: Session,
    finding_id: str,
    tenant_id: str = DEMO_TENANT,
    run_adversarial: bool = True,
    requested_by_user_id: str | None = None,
    submit_for_review: bool = True,
) -> SuggestResult:
    """``submit_for_review=False`` (what the API and Ask pass) only DRAFTS: the
    suggestion is persisted but not queued, so the requester can preview and
    optionally edit it first and then submit it via ``enqueue_for_review``.
    The default of True keeps direct pipeline callers/tests on the old
    draft-and-queue-in-one-step behaviour."""
    finding = store.find_finding_by_id(finding_id, tenant_id=tenant_id)
    if finding is None:
        raise SuggestInputError(f"Finding {finding_id!r} not found.")
    clause = store.get_clause_by_id(finding.clause_id, tenant_id=tenant_id)
    if clause is None:
        raise SuggestInputError(f"Clause {finding.clause_id!r} for finding {finding_id!r} not found.")

    ctx = await retrieve_context(
        store, clause, change_request=finding.explanation, finding=finding, tenant_id=tenant_id
    )
    return await _run_pipeline(
        db,
        ctx,
        clause,
        finding_id=finding_id,
        run_adversarial=run_adversarial,
        tenant_id=tenant_id,
        requested_by_user_id=requested_by_user_id,
        submit_for_review=submit_for_review,
    )


async def suggest_standalone(
    store: GraphStore,
    db: Session,
    contract_id: str,
    clause_id: str,
    change_request: str,
    tenant_id: str = DEMO_TENANT,
    run_adversarial: bool = True,
    requested_by_user_id: str | None = None,
    submit_for_review: bool = True,
) -> SuggestResult:
    clause = store.get_clause_by_id(clause_id, tenant_id=tenant_id)
    if clause is None:
        raise SuggestInputError(f"Clause {clause_id!r} not found.")
    if clause.contract_id != contract_id:
        raise SuggestInputError(
            f"Clause {clause_id!r} belongs to contract {clause.contract_id!r}, not {contract_id!r}."
        )

    ctx = await retrieve_context(
        store, clause, change_request=change_request, finding=None, tenant_id=tenant_id
    )
    # An edit that targets a clause with exactly ONE finding is a fix for that
    # finding, so the dashboard can count it. With several findings on the same
    # clause it is ambiguous which one it fixes, so it stays unlinked.
    on_clause = [
        f for f in store.get_findings(contract_id, tenant_id=tenant_id) if f.clause_id == clause_id
    ]
    linked_finding_id = on_clause[0].finding_id if len(on_clause) == 1 else None
    return await _run_pipeline(
        db,
        ctx,
        clause,
        finding_id=linked_finding_id,
        run_adversarial=run_adversarial,
        tenant_id=tenant_id,
        requested_by_user_id=requested_by_user_id,
        submit_for_review=submit_for_review,
    )


class SubmissionError(ValueError):
    """A user-facing 4xx-shaped error from submitting a draft."""


def enqueue_for_review(
    db: Session,
    suggestion: RedlineSuggestion,
    edited_text: str | None = None,
    source: str = "suggest_pipeline",
) -> Approval:
    """Puts a drafted suggestion in front of a reviewer as a pending Approval.
    If the requester edited the AI text, that edit is stored on the suggestion
    (never over the AI's own text). Raises if it's already been submitted."""
    if db.query(Approval).filter(Approval.redline_suggestion_id == suggestion.id).first():
        raise SubmissionError("This draft has already been submitted for review.")

    text = (edited_text or "").strip()
    edited = bool(text) and text != suggestion.proposed_text
    if edited:
        suggestion.requester_edited_text = text

    approval = Approval(redline_suggestion_id=suggestion.id, status="pending")
    db.add(approval)
    db.flush()  # assigns approval.id (the Python-side default) before it's referenced below
    db.add(
        AuditLog(
            event_type="approval_created",
            entity_id=approval.id,
            details=json.dumps(
                {"redline_suggestion_id": suggestion.id, "source": source, "requester_edited": edited}
            ),
        )
    )
    db.commit()
    db.refresh(approval)
    return approval


async def _run_pipeline(
    db: Session,
    ctx: RetrievedContext,
    clause: ExtractedClause,
    finding_id: str | None,
    run_adversarial: bool,
    tenant_id: str = DEMO_TENANT,
    requested_by_user_id: str | None = None,
    submit_for_review: bool = True,
) -> SuggestResult:
    redline = await draft_redline(ctx)

    contrarian = judge = negotiation = None
    final_confidence = redline.confidence
    if run_adversarial:
        contrarian = await run_contrarian(ctx)
        judge = await run_judge(ctx, redline.confidence, contrarian)
        final_confidence = judge.final_confidence
        if judge.verdict == "dismissed":
            logger.info(
                "Judge dismissed the finding for clause %s: %s", clause.clause_id, judge.reasoning
            )
        negotiation = await run_negotiation_twin(ctx, redline)

    row = RedlineSuggestion(
        tenant_id=tenant_id,
        requested_by_user_id=requested_by_user_id,
        finding_id=finding_id,
        contract_id=clause.contract_id,
        clause_id=clause.clause_id,
        original_clause_text=clause.raw_text,
        proposed_text=redline.proposed_clause_text,
        rationale=redline.rationale,
        confidence=final_confidence,
        contrarian_json=contrarian.model_dump_json() if contrarian else None,
        judge_json=judge.model_dump_json() if judge else None,
        negotiation_json=negotiation.model_dump_json() if negotiation else None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    approval = enqueue_for_review(db, row) if submit_for_review else None

    return SuggestResult(
        suggestion_id=row.id,
        finding_id=finding_id,
        contract_id=clause.contract_id,
        clause_id=clause.clause_id,
        proposed_text=redline.proposed_clause_text,
        rationale=redline.rationale,
        confidence=final_confidence,
        contrarian=contrarian,
        judge=judge,
        negotiation=negotiation,
        created_at=row.created_at,
        approval_id=approval.id if approval else None,
    )
