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

import logging

from sqlalchemy.orm import Session

from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.agents.suggest.adversarial_review import run_contrarian, run_judge
from app.agents.suggest.draft_redline import draft_redline
from app.agents.suggest.negotiation_twin import run_negotiation_twin
from app.agents.suggest.retriever import retrieve_context
from app.db.models import RedlineSuggestion
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
) -> SuggestResult:
    finding = store.find_finding_by_id(finding_id, tenant_id=tenant_id)
    if finding is None:
        raise SuggestInputError(f"Finding {finding_id!r} not found.")
    clause = store.get_clause_by_id(finding.clause_id, tenant_id=tenant_id)
    if clause is None:
        raise SuggestInputError(f"Clause {finding.clause_id!r} for finding {finding_id!r} not found.")

    ctx = await retrieve_context(
        store, clause, change_request=finding.explanation, finding=finding, tenant_id=tenant_id
    )
    return await _run_pipeline(db, ctx, clause, finding_id=finding_id, run_adversarial=run_adversarial)


async def suggest_standalone(
    store: GraphStore,
    db: Session,
    contract_id: str,
    clause_id: str,
    change_request: str,
    tenant_id: str = DEMO_TENANT,
    run_adversarial: bool = True,
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
    return await _run_pipeline(db, ctx, clause, finding_id=None, run_adversarial=run_adversarial)


async def _run_pipeline(
    db: Session,
    ctx: RetrievedContext,
    clause: ExtractedClause,
    finding_id: str | None,
    run_adversarial: bool,
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
        finding_id=finding_id,
        contract_id=clause.contract_id,
        clause_id=clause.clause_id,
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
    )
