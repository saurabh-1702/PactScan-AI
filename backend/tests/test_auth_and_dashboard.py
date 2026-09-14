"""Phase 5 — auth, role-gating, tenant isolation, and notifications.

Mocked/in-memory throughout (InMemoryGraphStore + SQLite via db_session) —
no Docker/Neo4j/Postgres needed, matching every prior phase's test suite.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents.detect.graph_store import DEMO_TENANT, InMemoryGraphStore
from app.agents.notifications.notify import notify_new_findings
from app.api.approvals import get_store as approvals_get_store
from app.api.dashboard import get_store as dashboard_get_store
from app.config import settings
from app.db.models import Approval, Notification, RedlineSuggestion, Tenant
from app.db.postgres_client import get_db
from app.main import app
from app.models.clause import ClauseType, ConfidenceLevel, Finding, Severity

TENANT_B = "tenant_b"


@pytest.fixture
def two_tenants(db_session):
    """DEMO_TENANT + a second tenant, each with one end_user/reviewer pair.
    DEMO_TENANT additionally gets a pending approval to decide against."""
    db_session.add(Tenant(id=DEMO_TENANT, name="Demo Tenant"))
    db_session.add(Tenant(id=TENANT_B, name="Tenant B"))
    db_session.commit()

    store = InMemoryGraphStore()

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[approvals_get_store] = lambda: store
    app.dependency_overrides[dashboard_get_store] = lambda: store

    client = TestClient(app)

    def _register_and_login(email: str, tenant_id: str, role: str) -> str:
        resp = client.post(
            "/api/auth/register",
            json={"email": email, "password": "TestPass123!", "tenant_id": tenant_id, "role": role},
        )
        assert resp.status_code == 200, resp.text
        return resp.json()["access_token"]

    tokens = {
        "a_end_user": _register_and_login("a_user@test.com", DEMO_TENANT, "end_user"),
        "a_reviewer": _register_and_login("a_reviewer@test.com", DEMO_TENANT, "reviewer"),
        "b_reviewer": _register_and_login("b_reviewer@test.com", TENANT_B, "reviewer"),
    }

    # -- DEMO_TENANT data: one pending approval + one finding --------------
    store.upsert_contract("ct_a", "contract_a.pdf", tenant_id=DEMO_TENANT)
    finding_a = Finding(
        finding_id="fnd_a",
        clause_id="cl_a",
        clause_type=ClauseType.LIMITATION_OF_LIABILITY,
        page_number=1,
        section_header="Section 1",
        severity=Severity.HIGH,
        rule_or_regulation_violated="dpdp_s8",
        explanation="test finding A",
        confidence=ConfidenceLevel.high,
    )
    store.replace_findings("ct_a", [finding_a], tenant_id=DEMO_TENANT)

    suggestion_a = RedlineSuggestion(
        tenant_id=DEMO_TENANT,
        finding_id="fnd_a",
        contract_id="ct_a",
        clause_id="cl_a",
        proposed_text="proposed",
        rationale="rationale",
        confidence=70,
    )
    db_session.add(suggestion_a)
    db_session.flush()
    approval_a = Approval(redline_suggestion_id=suggestion_a.id, status="pending")
    db_session.add(approval_a)
    db_session.commit()

    # -- TENANT_B data: a completely separate contract/finding/suggestion --
    store.upsert_contract("ct_b", "contract_b.pdf", tenant_id=TENANT_B)
    finding_b = Finding(
        finding_id="fnd_b",
        clause_id="cl_b",
        clause_type=ClauseType.GOVERNING_LAW,
        page_number=1,
        section_header="Section 1",
        severity=Severity.MEDIUM,
        rule_or_regulation_violated="dpdp_s9",
        explanation="test finding B",
        confidence=ConfidenceLevel.high,
    )
    store.replace_findings("ct_b", [finding_b], tenant_id=TENANT_B)

    suggestion_b = RedlineSuggestion(
        tenant_id=TENANT_B,
        finding_id="fnd_b",
        contract_id="ct_b",
        clause_id="cl_b",
        proposed_text="proposed b",
        rationale="rationale b",
        confidence=70,
    )
    db_session.add(suggestion_b)
    db_session.flush()
    db_session.add(Approval(redline_suggestion_id=suggestion_b.id, status="pending"))
    db_session.commit()

    try:
        yield {
            "client": client,
            "db": db_session,
            "store": store,
            "tokens": tokens,
            "approval_a_id": approval_a.id,
        }
    finally:
        app.dependency_overrides.clear()


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# --------------------------------------------------------------------------- #
# Login
# --------------------------------------------------------------------------- #
def test_login_success_and_failure(two_tenants):
    client = two_tenants["client"]

    ok = client.post(
        "/api/auth/login", json={"email": "a_reviewer@test.com", "password": "TestPass123!"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["access_token"]
    assert ok.json()["role"] == "reviewer"
    assert ok.json()["tenant_id"] == DEMO_TENANT

    bad = client.post(
        "/api/auth/login", json={"email": "a_reviewer@test.com", "password": "wrong-password"}
    )
    assert bad.status_code == 401


# --------------------------------------------------------------------------- #
# Role gating on the Executor's only entry point
# --------------------------------------------------------------------------- #
def test_end_user_forbidden_reviewer_allowed_on_decide(two_tenants):
    client = two_tenants["client"]
    approval_id = two_tenants["approval_a_id"]
    tokens = two_tenants["tokens"]

    forbidden = client.post(
        f"/api/approvals/{approval_id}/decide",
        json={"decision": "rejected"},
        headers=_auth(tokens["a_end_user"]),
    )
    assert forbidden.status_code == 403

    allowed = client.post(
        f"/api/approvals/{approval_id}/decide",
        json={"decision": "rejected"},
        headers=_auth(tokens["a_reviewer"]),
    )
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["status"] == "rejected"


def test_missing_token_is_401():
    client = TestClient(app)
    resp = client.get("/api/dashboard/overview")
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Tenant isolation — the exit-criteria test
# --------------------------------------------------------------------------- #
def test_dashboard_and_approvals_never_leak_across_tenants(two_tenants):
    client = two_tenants["client"]
    tokens = two_tenants["tokens"]

    overview_a = client.get("/api/dashboard/overview", headers=_auth(tokens["a_reviewer"])).json()
    assert overview_a["total_contracts"] == 1
    assert overview_a["findings_by_severity"]["HIGH"] == 1
    assert overview_a["findings_by_severity"]["MEDIUM"] == 0  # tenant B's finding must not appear

    overview_b = client.get("/api/dashboard/overview", headers=_auth(tokens["b_reviewer"])).json()
    assert overview_b["total_contracts"] == 1
    assert overview_b["findings_by_severity"]["MEDIUM"] == 1
    assert overview_b["findings_by_severity"]["HIGH"] == 0  # tenant A's finding must not appear

    pipeline_a = client.get(
        "/api/dashboard/findings-pipeline", headers=_auth(tokens["a_reviewer"])
    ).json()
    all_ids_a = [f["finding_id"] for bucket in pipeline_a.values() for f in bucket]
    assert "fnd_a" in all_ids_a
    assert "fnd_b" not in all_ids_a

    approvals_a = client.get("/api/approvals", headers=_auth(tokens["a_reviewer"])).json()
    assert all(a["contract_id"] == "ct_a" for a in approvals_a)

    approvals_b = client.get("/api/approvals", headers=_auth(tokens["b_reviewer"])).json()
    assert all(a["contract_id"] == "ct_b" for a in approvals_b)


# --------------------------------------------------------------------------- #
# Notifications
# --------------------------------------------------------------------------- #
def test_high_severity_finding_creates_notification_row(db_session, monkeypatch):
    # Force email off regardless of what backend\.env has configured — a
    # mocked test must never risk a real Resend API call. Email delivery
    # itself is verified manually, not by an automated live test (see
    # docs/SETUP_NOTES.md).
    monkeypatch.setattr(settings, "resend_api_key", "")

    high = Finding(
        finding_id="fnd_high",
        clause_id="cl_high",
        clause_type=ClauseType.LIMITATION_OF_LIABILITY,
        page_number=1,
        section_header="Section 1",
        severity=Severity.HIGH,
        rule_or_regulation_violated="dpdp_s8",
        explanation="high severity test finding",
        confidence=ConfidenceLevel.high,
    )
    low = Finding(
        finding_id="fnd_low",
        clause_id="cl_low",
        clause_type=ClauseType.GOVERNING_LAW,
        page_number=1,
        section_header="Section 2",
        severity=Severity.LOW,
        rule_or_regulation_violated="dpdp_s9",
        explanation="low severity test finding",
        confidence=ConfidenceLevel.high,
    )

    notify_new_findings(db_session, DEMO_TENANT, "contract_x.pdf", [high, low])

    rows = db_session.query(Notification).filter(Notification.tenant_id == DEMO_TENANT).all()
    assert {r.finding_id for r in rows} == {"fnd_high", "fnd_low"}
    high_row = next(r for r in rows if r.finding_id == "fnd_high")
    assert high_row.severity == "HIGH"
    assert not high_row.is_read
    assert "contract_x.pdf" in high_row.message
