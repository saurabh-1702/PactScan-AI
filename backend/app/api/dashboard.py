"""Dashboard API (Phase 5) — read-only visualization over data Phases 1-3
already computed. Nothing here runs a new Detect/Suggest/Fix pass.

GET /api/dashboard/overview           -> counts: contracts, findings by
                                          severity, approvals by status
GET /api/dashboard/findings-pipeline  -> findings grouped by current stage,
                                          derived by joining Neo4j findings
                                          with Postgres suggestions/approvals
                                          (no separately-maintained status field)
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.agents.detect.graph_store import GraphStore, get_graph_store
from app.api.access import owner_scope, visible_contract_ids
from app.api.deps import CurrentUser, get_current_user
from app.db.models import Approval, RedlineSuggestion
from app.db.postgres_client import get_db
from app.models.dashboard import DashboardOverview, FindingsPipeline, PipelineFinding

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def get_store() -> GraphStore:
    return get_graph_store()


@router.get("/overview", response_model=DashboardOverview)
def overview(
    store: GraphStore = Depends(get_store),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> DashboardOverview:
    # end_user: only contracts they uploaded; reviewer/admin: whole tenant
    findings = store.get_all_findings(
        tenant_id=current_user.tenant_id, owner_user_id=owner_scope(current_user)
    )
    visible = visible_contract_ids(store, current_user)
    findings_by_severity = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        findings_by_severity[f["severity"]] = findings_by_severity.get(f["severity"], 0) + 1

    approvals_by_status = {"pending": 0, "approved": 0, "rejected": 0}
    q = (
        db.query(Approval.status)
        .join(RedlineSuggestion, Approval.redline_suggestion_id == RedlineSuggestion.id)
        .filter(RedlineSuggestion.tenant_id == current_user.tenant_id)
    )
    if visible is not None:
        q = q.filter(RedlineSuggestion.contract_id.in_(visible))
    rows = q.all()
    for (status,) in rows:
        approvals_by_status[status] = approvals_by_status.get(status, 0) + 1

    return DashboardOverview(
        total_contracts=len(
            store.list_contracts(
                tenant_id=current_user.tenant_id, owner_user_id=owner_scope(current_user)
            )
        ),
        findings_by_severity=findings_by_severity,
        approvals_by_status=approvals_by_status,
    )


@router.get("/findings-pipeline", response_model=FindingsPipeline)
def findings_pipeline(
    store: GraphStore = Depends(get_store),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> FindingsPipeline:
    findings = store.get_all_findings(
        tenant_id=current_user.tenant_id, owner_user_id=owner_scope(current_user)
    )
    visible = visible_contract_ids(store, current_user)

    sq = db.query(RedlineSuggestion).filter(RedlineSuggestion.tenant_id == current_user.tenant_id)
    if visible is not None:
        sq = sq.filter(RedlineSuggestion.contract_id.in_(visible))
    suggestions = sq.all()

    approval_status_by_suggestion: dict[str, str] = {}
    if suggestions:
        approvals = (
            db.query(Approval)
            .filter(Approval.redline_suggestion_id.in_([s.id for s in suggestions]))
            .order_by(Approval.created_at.desc())
            .all()
        )
        for a in approvals:
            approval_status_by_suggestion.setdefault(a.redline_suggestion_id, a.status)

    # A finding can have several drafts (re-drafted, drafted from Ask, ...). Its
    # stage is that of the FURTHEST-ADVANCED one — so a newer, still-unsubmitted
    # draft can't hide an older one that is already with a reviewer.
    stage_of = {
        None: ("redline_suggested", 1),
        "pending": ("pending_approval", 2),
        "approved": ("fixed_applied", 3),
        "rejected": ("rejected", 0),
    }
    best_stage_by_finding: dict[str, tuple[str, int]] = {}
    for s in suggestions:
        if not s.finding_id:
            continue
        stage = stage_of.get(approval_status_by_suggestion.get(s.id), stage_of[None])
        current = best_stage_by_finding.get(s.finding_id)
        if current is None or stage[1] > current[1]:
            best_stage_by_finding[s.finding_id] = stage

    buckets: dict[str, list[PipelineFinding]] = {
        "new_finding": [],
        "redline_suggested": [],
        "pending_approval": [],
        "fixed_applied": [],
        "rejected": [],
    }
    for f in findings:
        item = PipelineFinding(
            finding_id=f["finding_id"],
            contract_id=f["contract_id"],
            severity=f["severity"],
            rule_or_regulation_violated=f["rule_or_regulation_violated"],
        )
        best = best_stage_by_finding.get(f["finding_id"])
        buckets[best[0] if best else "new_finding"].append(item)

    return FindingsPipeline(**buckets)
