"""Deleting unsubmitted drafts, renaming/deleting Ask conversations, and the
dashboard's "where findings stand" counting. In-memory graph + SQLite."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.agents.detect.graph_store import DEMO_TENANT, InMemoryGraphStore
from app.agents.suggest import pipeline as suggest_pipeline
from app.api.approvals import get_store as approvals_get_store
from app.api.dashboard import get_store as dashboard_get_store
from app.api.deps import CurrentUser, get_current_user
from app.api.my_drafts import get_store as drafts_get_store
from app.db.models import Approval, AuditLog, ChatMessage, ChatSession, RedlineSuggestion
from app.db.postgres_client import get_db
from app.main import app
from app.models.clause import ClauseType, ConfidenceLevel, ExtractedClause, Finding, Severity

ALICE = CurrentUser(user_id="usr_alice", tenant_id=DEMO_TENANT, role="end_user")
BOB = CurrentUser(user_id="usr_bob", tenant_id=DEMO_TENANT, role="end_user")


def _finding(fid: str, clause_id: str, severity: Severity = Severity.HIGH) -> Finding:
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


def _clause(cid: str, contract_id: str) -> ExtractedClause:
    return ExtractedClause(
        clause_id=cid,
        contract_id=contract_id,
        clause_type=ClauseType.DATA_PROCESSING,
        page_number=1,
        section_header="S",
        raw_text="text",
        confidence=ConfidenceLevel.high,
    )


@pytest.fixture
def world(db_session):
    store = InMemoryGraphStore()
    store.upsert_contract("ct_a", "a.pdf", tenant_id=DEMO_TENANT, uploaded_by_user_id=ALICE.user_id)
    store.upsert_contract("ct_b", "b.pdf", tenant_id=DEMO_TENANT, uploaded_by_user_id=ALICE.user_id)
    for cid in ("cl_1", "cl_2"):
        store.add_clause(_clause(cid, "ct_a"), tenant_id=DEMO_TENANT)
    store.add_clause(_clause("cl_b", "ct_b"), tenant_id=DEMO_TENANT)
    store.replace_findings(
        "ct_a",
        [_finding("fnd_1", "cl_1"), _finding("fnd_2", "cl_2", Severity.MEDIUM)],
        tenant_id=DEMO_TENANT,
    )
    store.replace_findings("ct_b", [_finding("fnd_b", "cl_b")], tenant_id=DEMO_TENANT)

    def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    for getter in (dashboard_get_store, drafts_get_store, approvals_get_store):
        app.dependency_overrides[getter] = lambda: store
    try:
        yield {"store": store, "db": db_session, "client": TestClient(app)}
    finally:
        app.dependency_overrides.clear()


def _as(user: CurrentUser):
    app.dependency_overrides[get_current_user] = lambda: user


def _draft(db, owner: CurrentUser, contract="ct_a", clause="cl_1", finding="fnd_1", status=None):
    sg = RedlineSuggestion(
        tenant_id=DEMO_TENANT,
        requested_by_user_id=owner.user_id,
        finding_id=finding,
        contract_id=contract,
        clause_id=clause,
        proposed_text="p",
        rationale="r",
        confidence=50,
    )
    db.add(sg)
    db.flush()
    if status:
        db.add(Approval(redline_suggestion_id=sg.id, status=status))
    db.commit()
    return sg


# --------------------------------------------------------------- delete drafts
def test_an_unsubmitted_draft_can_be_deleted_and_the_deletion_is_audited(world):
    db, client = world["db"], world["client"]
    sg = _draft(db, ALICE)
    _as(ALICE)

    assert client.delete(f"/api/my-drafts/{sg.id}").json() == {"deleted": 1}
    assert db.get(RedlineSuggestion, sg.id) is None
    assert client.get("/api/my-drafts").json() == []
    assert db.query(AuditLog).filter_by(event_type="draft_deleted", entity_id=sg.id).count() == 1


@pytest.mark.parametrize("status", ["pending", "approved", "rejected"])
def test_a_submitted_draft_can_never_be_deleted(world, status):
    db, client = world["db"], world["client"]
    sg = _draft(db, ALICE, status=status)
    _as(ALICE)

    resp = client.delete(f"/api/my-drafts/{sg.id}")
    assert resp.status_code == 409
    assert db.get(RedlineSuggestion, sg.id) is not None


def test_you_cannot_delete_someone_elses_draft_and_cannot_tell_it_exists(world):
    db, client = world["db"], world["client"]
    sg = _draft(db, ALICE)
    _as(BOB)
    assert client.delete(f"/api/my-drafts/{sg.id}").status_code == 404
    assert client.delete("/api/my-drafts/sg_does_not_exist").status_code == 404
    assert db.get(RedlineSuggestion, sg.id) is not None


def test_bulk_delete_removes_only_my_unsubmitted_drafts_for_that_contract(world):
    db, client = world["db"], world["client"]
    mine_1 = _draft(db, ALICE)
    mine_2 = _draft(db, ALICE, clause="cl_2", finding="fnd_2")
    submitted = _draft(db, ALICE, status="pending")
    other_contract = _draft(db, ALICE, contract="ct_b", clause="cl_b", finding="fnd_b")
    bobs = _draft(db, BOB)
    _as(ALICE)

    assert client.delete("/api/my-drafts", params={"contract_id": "ct_a"}).json() == {"deleted": 2}
    assert db.get(RedlineSuggestion, mine_1.id) is None
    assert db.get(RedlineSuggestion, mine_2.id) is None
    for keep in (submitted, other_contract, bobs):
        assert db.get(RedlineSuggestion, keep.id) is not None


# ------------------------------------------------------ rename / delete chats
def _session(db, owner: CurrentUser, title="Old title") -> ChatSession:
    s = ChatSession(tenant_id=DEMO_TENANT, user_id=owner.user_id, title=title)
    db.add(s)
    db.flush()
    db.add(ChatMessage(session_id=s.id, role="user", content="hi"))
    db.commit()
    return s


def test_rename_a_conversation_trims_and_collapses_whitespace(world):
    db, client = world["db"], world["client"]
    s = _session(db, ALICE)
    _as(ALICE)

    resp = client.patch(f"/api/ask/sessions/{s.id}", json={"title": "  Liability   review  "})
    assert resp.status_code == 200
    assert resp.json()["title"] == "Liability review"
    assert client.get("/api/ask/sessions").json()[0]["title"] == "Liability review"


@pytest.mark.parametrize("title", ["", "   ", "x" * 81])
def test_rename_rejects_empty_and_overlong_titles(world, title):
    db, client = world["db"], world["client"]
    s = _session(db, ALICE)
    _as(ALICE)
    assert client.patch(f"/api/ask/sessions/{s.id}", json={"title": title}).status_code == 422
    assert db.get(ChatSession, s.id).title == "Old title"


def test_you_cannot_rename_or_delete_someone_elses_conversation(world):
    db, client = world["db"], world["client"]
    s = _session(db, ALICE)
    _as(BOB)
    assert client.patch(f"/api/ask/sessions/{s.id}", json={"title": "Mine now"}).status_code == 404
    assert client.delete(f"/api/ask/sessions/{s.id}").status_code == 404
    assert db.get(ChatSession, s.id).title == "Old title"


def test_deleting_a_conversation_removes_its_messages_but_not_its_drafts(world):
    db, client = world["db"], world["client"]
    s = _session(db, ALICE)
    sg = _draft(db, ALICE)
    _as(ALICE)

    assert client.delete(f"/api/ask/sessions/{s.id}").json() == {"deleted": 1}
    assert db.get(ChatSession, s.id) is None
    assert db.query(ChatMessage).filter_by(session_id=s.id).count() == 0
    assert db.get(RedlineSuggestion, sg.id) is not None


# ------------------------------------------------------------------ dashboard
def _stages(client) -> dict[str, list[str]]:
    body = client.get("/api/dashboard/findings-pipeline").json()
    return {k: sorted(f["finding_id"] for f in v) for k, v in body.items()}


def test_two_drafts_on_two_findings_both_count_as_in_review(world):
    db, client = world["db"], world["client"]
    _draft(db, ALICE, clause="cl_1", finding="fnd_1", status="pending")
    _draft(db, ALICE, clause="cl_2", finding="fnd_2", status="pending")
    _as(ALICE)

    stages = _stages(client)
    assert stages["pending_approval"] == ["fnd_1", "fnd_2"]
    assert client.get("/api/dashboard/overview").json()["approvals_by_status"]["pending"] == 2


def test_the_furthest_stage_wins_so_a_newer_unsubmitted_draft_cannot_hide_a_pending_one(world):
    db, client = world["db"], world["client"]
    _draft(db, ALICE, status="pending")
    _draft(db, ALICE)  # a newer draft for the same finding, not submitted
    _as(ALICE)

    stages = _stages(client)
    assert stages["pending_approval"] == ["fnd_1"]
    assert "fnd_1" not in stages["redline_suggested"]


def test_stage_precedence_approved_over_pending_over_draft_over_rejected(world):
    db, client = world["db"], world["client"]
    _draft(db, ALICE, clause="cl_1", finding="fnd_1", status="rejected")
    _draft(db, ALICE, clause="cl_1", finding="fnd_1")  # redrafted after the rejection
    _draft(db, ALICE, clause="cl_2", finding="fnd_2", status="rejected")
    _draft(db, ALICE, contract="ct_b", clause="cl_b", finding="fnd_b", status="pending")
    _draft(db, ALICE, contract="ct_b", clause="cl_b", finding="fnd_b", status="approved")
    _as(ALICE)

    stages = _stages(client)
    assert stages["redline_suggested"] == ["fnd_1"]
    assert stages["rejected"] == ["fnd_2"]
    assert stages["fixed_applied"] == ["fnd_b"]


def test_a_finding_with_no_draft_is_still_new(world):
    _as(ALICE)
    assert _stages(world["client"])["new_finding"] == ["fnd_1", "fnd_2", "fnd_b"]


# ------------------------------------------- Ask drafts link to a finding
@pytest.mark.asyncio
async def test_an_ask_edit_links_to_the_clauses_finding_only_when_unambiguous(world, monkeypatch):
    store, db = world["store"], world["db"]
    captured: list[str | None] = []

    async def _ctx(*a, **k):
        return None

    async def _run(db_, ctx, clause, finding_id, **k):
        captured.append(finding_id)

    monkeypatch.setattr(suggest_pipeline, "retrieve_context", _ctx)
    monkeypatch.setattr(suggest_pipeline, "_run_pipeline", _run)

    # cl_1 has exactly one finding -> linked
    await suggest_pipeline.suggest_standalone(store, db, "ct_a", "cl_1", "change it")
    # give cl_2 a second finding -> ambiguous -> unlinked
    store.replace_findings(
        "ct_a",
        [_finding("fnd_1", "cl_1"), _finding("fnd_2", "cl_2"), _finding("fnd_3", "cl_2")],
        tenant_id=DEMO_TENANT,
    )
    await suggest_pipeline.suggest_standalone(store, db, "ct_a", "cl_2", "change it")
    # a clause with no finding at all -> unlinked
    store.replace_findings("ct_a", [_finding("fnd_1", "cl_1")], tenant_id=DEMO_TENANT)
    await suggest_pipeline.suggest_standalone(store, db, "ct_a", "cl_2", "change it")

    assert captured == ["fnd_1", None, None]
