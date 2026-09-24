"""Phase 6b — an end_user only sees contracts they uploaded; reviewers and
admins see the whole tenant. Covers the dashboard, contract pages, approvals,
notifications, and Ask's portfolio search. In-memory graph + SQLite."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents.ask.ask_retriever import retrieve_for_content_question
from app.agents.detect.graph_store import DEMO_TENANT, InMemoryGraphStore
from app.agents.notifications.notify import notify_new_findings
from app.api.approvals import get_store as approvals_get_store
from app.api.dashboard import get_store as dashboard_get_store
from app.api.deps import CurrentUser, get_current_user
from app.api.detect import get_store as detect_get_store
from app.db.models import Approval, RedlineSuggestion
from app.db.postgres_client import get_db
from app.main import app
from app.models.ask import DocumentScope
from app.models.clause import ClauseType, ConfidenceLevel, ExtractedClause, Finding, Severity

ALICE = CurrentUser(user_id="usr_alice", tenant_id=DEMO_TENANT, role="end_user")
BOB = CurrentUser(user_id="usr_bob", tenant_id=DEMO_TENANT, role="end_user")
REVIEWER = CurrentUser(user_id="usr_rev", tenant_id=DEMO_TENANT, role="reviewer")


def _finding(fid: str, clause_id: str, severity: Severity) -> Finding:
    return Finding(
        finding_id=fid,
        clause_id=clause_id,
        clause_type=ClauseType.DATA_PROCESSING,
        page_number=1,
        section_header="S",
        severity=severity,
        rule_or_regulation_violated="rule",
        explanation="why",
        confidence=ConfidenceLevel.high,
    )


@pytest.fixture
def world(db_session):
    store = InMemoryGraphStore()
    for cid, fname, owner, clause_id, sev in [
        ("ct_alice", "alice.pdf", ALICE.user_id, "cl_alice", Severity.HIGH),
        ("ct_bob", "bob.pdf", BOB.user_id, "cl_bob", Severity.LOW),
    ]:
        store.upsert_contract(cid, fname, tenant_id=DEMO_TENANT, uploaded_by_user_id=owner)
        store.add_clause(
            ExtractedClause(
                clause_id=clause_id,
                contract_id=cid,
                clause_type=ClauseType.DATA_PROCESSING,
                page_number=1,
                section_header="S",
                raw_text=f"clause text of {fname}",
                confidence=ConfidenceLevel.high,
            ),
            tenant_id=DEMO_TENANT,
        )
        store.set_clause_embedding(clause_id, [1.0, 0.0], tenant_id=DEMO_TENANT)
        store.replace_findings(cid, [_finding(f"fnd_{cid}", clause_id, sev)], tenant_id=DEMO_TENANT)

        sg = RedlineSuggestion(
            tenant_id=DEMO_TENANT,
            requested_by_user_id=owner,
            finding_id=f"fnd_{cid}",
            contract_id=cid,
            clause_id=clause_id,
            proposed_text="p",
            rationale="r",
            confidence=50,
        )
        db_session.add(sg)
        db_session.flush()
        db_session.add(Approval(redline_suggestion_id=sg.id, status="pending"))
    db_session.commit()

    def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    for getter in (dashboard_get_store, detect_get_store, approvals_get_store):
        app.dependency_overrides[getter] = lambda: store
    try:
        yield {"store": store, "db": db_session, "client": TestClient(app)}
    finally:
        app.dependency_overrides.clear()


def _as(user: CurrentUser):
    app.dependency_overrides[get_current_user] = lambda: user


def test_dashboard_is_scoped_to_the_end_users_own_contracts(world):
    client = world["client"]

    _as(ALICE)
    mine = client.get("/api/dashboard/overview").json()
    assert mine["total_contracts"] == 1
    assert mine["findings_by_severity"] == {"HIGH": 1, "MEDIUM": 0, "LOW": 0}
    assert mine["approvals_by_status"]["pending"] == 1

    pipeline = client.get("/api/dashboard/findings-pipeline").json()
    ids = [f["finding_id"] for bucket in pipeline.values() for f in bucket]
    assert ids == ["fnd_ct_alice"]

    _as(REVIEWER)
    everyone = client.get("/api/dashboard/overview").json()
    assert everyone["total_contracts"] == 2
    assert everyone["findings_by_severity"]["HIGH"] == 1
    assert everyone["findings_by_severity"]["LOW"] == 1
    assert everyone["approvals_by_status"]["pending"] == 2


def test_end_user_cannot_open_someone_elses_contract_but_reviewer_can(world):
    client = world["client"]

    _as(ALICE)
    assert client.get("/api/detect/ct_alice").status_code == 200
    assert client.get("/api/detect/ct_bob").status_code == 404

    _as(REVIEWER)
    assert client.get("/api/detect/ct_bob").status_code == 200


def test_approvals_list_is_scoped_for_end_users(world):
    client = world["client"]

    _as(ALICE)
    assert {a["contract_id"] for a in client.get("/api/approvals").json()} == {"ct_alice"}

    _as(REVIEWER)
    assert {a["contract_id"] for a in client.get("/api/approvals").json()} == {"ct_alice", "ct_bob"}


def test_new_finding_notifications_only_reach_the_contracts_owner_and_reviewers(world):
    db, client = world["db"], world["client"]
    notify_new_findings(
        db, DEMO_TENANT, "alice.pdf", [_finding("f1", "cl_alice", Severity.LOW)],
        contract_owner_user_id=ALICE.user_id,
    )
    notify_new_findings(
        db, DEMO_TENANT, "bob.pdf", [_finding("f2", "cl_bob", Severity.LOW)],
        contract_owner_user_id=BOB.user_id,
    )

    _as(ALICE)
    assert {n["finding_id"] for n in client.get("/api/notifications").json()} == {"f1"}
    _as(BOB)
    assert {n["finding_id"] for n in client.get("/api/notifications").json()} == {"f2"}
    _as(REVIEWER)
    assert {n["finding_id"] for n in client.get("/api/notifications").json()} == {"f1", "f2"}


@pytest.mark.asyncio
async def test_ask_portfolio_search_is_limited_to_the_end_users_contracts(world, monkeypatch):
    async def _embed(text):
        return [1.0, 0.0]

    monkeypatch.setattr("app.llm.client.generate_embedding", _embed)
    store = world["store"]

    mine = await retrieve_for_content_question(
        store, "anything", DocumentScope.PORTFOLIO, None, tenant_id=DEMO_TENANT,
        owner_user_id=ALICE.user_id,
    )
    cited = {i.document_name for i in mine.items if i.page_number > 0}
    assert cited == {"alice.pdf"}

    everyone = await retrieve_for_content_question(
        store, "anything", DocumentScope.PORTFOLIO, None, tenant_id=DEMO_TENANT,
        owner_user_id=None,
    )
    assert {i.document_name for i in everyone.items if i.page_number > 0} == {"alice.pdf", "bob.pdf"}

    # naming another user's document must not find it
    theirs = await retrieve_for_content_question(
        store, "anything", DocumentScope.SINGLE, "bob.pdf", tenant_id=DEMO_TENANT,
        owner_user_id=ALICE.user_id,
    )
    assert theirs.abstain is True
