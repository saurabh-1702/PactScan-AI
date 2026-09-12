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
    findings = store.get_all_findings(tenant_id=current_user.tenant_id)
    findings_by_severity = {"HIGH": 0, "MEDIUM": 0, "LOW": 0}
    for f in findings:
        findings_by_severity[f["severity"]] = findings_by_severity.get(f["severity"], 0) + 1

    approvals_by_status = {"pending": 0, "approved": 0, "rejected": 0}
    rows = (
        db.query(Approval.status)
        .join(RedlineSuggestion, Approval.redline_suggestion_id == RedlineSuggestion.id)
        .filter(RedlineSuggestion.tenant_id == current_user.tenant_id)
        .all()
    )
    for (status,) in rows:
        approvals_by_status[status] = approvals_by_status.get(status, 0) + 1

    return DashboardOverview(
        total_contracts=len(store.list_contracts(tenant_id=current_user.tenant_id)),
        findings_by_severity=findings_by_severity,
        approvals_by_status=approvals_by_status,
    )


@router.get("/findings-pipeline", response_model=FindingsPipeline)
def findings_pipeline(
    store: GraphStore = Depends(get_store),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> FindingsPipeline:
    findings = store.get_all_findings(tenant_id=current_user.tenant_id)

    suggestions = (
        db.query(RedlineSuggestion)
        .filter(RedlineSuggestion.tenant_id == current_user.tenant_id)
        .order_by(RedlineSuggestion.created_at.desc())
        .all()
    )
    # latest suggestion per finding_id wins, for a finding re-suggested more than once
    latest_suggestion_by_finding: dict[str, RedlineSuggestion] = {}
    for s in suggestions:
        if s.finding_id and s.finding_id not in latest_suggestion_by_finding:
            latest_suggestion_by_finding[s.finding_id] = s

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
        suggestion = latest_suggestion_by_finding.get(f["finding_id"])
        if suggestion is None:
            buckets["new_finding"].append(item)
            continue
        approval_status = approval_status_by_suggestion.get(suggestion.id)
        stage = {
            None: "redline_suggested",
            "pending": "pending_approval",
            "approved": "fixed_applied",
            "rejected": "rejected",
        }.get(approval_status, "redline_suggested")
        buckets[stage].append(item)

    return FindingsPipeline(**buckets)
