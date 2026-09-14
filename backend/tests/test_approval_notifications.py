"""Phase 5 — closing the loop back to whoever requested a draft, once a
reviewer/admin decides it. Covers all three outcomes: rejected (with the
reviewer's note), approved as-drafted (with a download link), and approved
but reviewer-edited (a distinct message, since the requester's exact wording
wasn't used). Mocked LLM + embeddings + LlamaParse, in-memory graph + SQLite.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.detect.graph_store import DEMO_TENANT, InMemoryGraphStore
from app.agents.detect.pipeline import ingest_and_detect
from app.agents.detect.seed_data import seed
from app.agents.suggest.pipeline import suggest_from_finding
from app.api.approvals import get_store as approvals_get_store
from app.api.deps import CurrentUser, get_current_user
from app.db.models import Approval, Notification
from app.db.postgres_client import get_db
from app.main import app
from tests.conftest import _CANNED_DOCS, _FakeLLM, _fake_embedding_vector

REQUESTER_ID = "usr_end_user_requester"
REVIEWER_ID = "usr_reviewer_decider"


def _wire_fakes(monkeypatch):
    fake = _FakeLLM()
    monkeypatch.setattr("app.llm.client.generate_structured", fake.generate_structured)
    monkeypatch.setattr("app.llm.client.generate_text", fake.generate_text)

    async def _embed(text):
        return _fake_embedding_vector(text)

    monkeypatch.setattr("app.llm.client.generate_embedding", _embed)
    monkeypatch.setattr(
        "app.agents.detect.ingest.parse_document",
        lambda p: _CANNED_DOCS[Path(p).name](),
    )


@pytest.fixture
def scenario(monkeypatch, fixture_pdf, db_session):
    """A draft explicitly requested by REQUESTER_ID, pending decision by
    REVIEWER_ID — same shape as test_approval_gate.py's fixture, but tracking
    who asked for it."""
    _wire_fakes(monkeypatch)
    store = InMemoryGraphStore()
    seed(store)

    async def _build():
        report = await ingest_and_detect(
            store,
            fixture_pdf("contract_a_conflict.pdf"),
            "contract_a_conflict.pdf",
            contract_id="ct_notif_test",
            db=db_session,
        )
        finding = next(f for f in report.findings if len(f.override_chain) >= 2)
        return await suggest_from_finding(
            store, db_session, finding.finding_id, requested_by_user_id=REQUESTER_ID
        )

    result = asyncio.run(_build())
    approval = (
        db_session.query(Approval)
        .filter(Approval.redline_suggestion_id == result.suggestion_id)
        .one()
    )

    def _override_get_db():
        yield db_session

    app.dependency_overrides[approvals_get_store] = lambda: store
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=REVIEWER_ID, tenant_id=DEMO_TENANT, role="reviewer"
    )
    try:
        yield {"client": TestClient(app), "db": db_session, "approval": approval}
    finally:
        app.dependency_overrides.clear()


def _notifications_for(db, user_id):
    return db.query(Notification).filter(Notification.recipient_user_id == user_id).all()


def test_rejected_notifies_requester_with_reviewers_note(scenario):
    client, db, approval = scenario["client"], scenario["db"], scenario["approval"]

    resp = client.post(
        f"/api/approvals/{approval.id}/decide",
        json={"decision": "rejected", "note": "This cap is still too low for our risk tolerance."},
    )
    assert resp.status_code == 200, resp.text

    notes = _notifications_for(db, REQUESTER_ID)
    assert len(notes) == 1
    assert notes[0].kind == "approval_decided"
    assert "rejected" in notes[0].message
    assert "This cap is still too low for our risk tolerance." in notes[0].message
    assert notes[0].document_version_id is None

    # the reviewer must not notify themselves for their own decision
    assert _notifications_for(db, REVIEWER_ID) == []


def test_approved_as_drafted_notifies_requester_with_download_link(scenario):
    client, db, approval = scenario["client"], scenario["db"], scenario["approval"]

    resp = client.post(f"/api/approvals/{approval.id}/decide", json={"decision": "approved"})
    assert resp.status_code == 200, resp.text

    notes = _notifications_for(db, REQUESTER_ID)
    assert len(notes) == 1
    assert "approved and applied" in notes[0].message
    assert "edited" not in notes[0].message.lower()
    assert notes[0].document_version_id is not None


def test_approved_with_reviewer_edit_notifies_requester_differently(scenario):
    client, db, approval = scenario["client"], scenario["db"], scenario["approval"]

    resp = client.post(
        f"/api/approvals/{approval.id}/decide",
        json={"decision": "approved", "edited_text": "A completely different, reviewer-written clause."},
    )
    assert resp.status_code == 200, resp.text

    notes = _notifications_for(db, REQUESTER_ID)
    assert len(notes) == 1
    assert "wrote their own edit" in notes[0].message
    assert notes[0].document_version_id is not None


def test_requester_sees_targeted_notification_via_api_but_others_dont(scenario):
    """The requester's own GET /api/notifications must include this targeted
    notification; a different user in the same tenant must not see it (only
    tenant-broadcast new_finding notifications are shared)."""
    client, db, approval = scenario["client"], scenario["db"], scenario["approval"]
    client.post(f"/api/approvals/{approval.id}/decide", json={"decision": "approved"})

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id=REQUESTER_ID, tenant_id=DEMO_TENANT, role="end_user"
    )
    mine = client.get("/api/notifications").json()
    assert any(n["kind"] == "approval_decided" for n in mine)

    app.dependency_overrides[get_current_user] = lambda: CurrentUser(
        user_id="usr_someone_else", tenant_id=DEMO_TENANT, role="end_user"
    )
    someone_elses = client.get("/api/notifications").json()
    assert not any(n["kind"] == "approval_decided" for n in someone_elses)
