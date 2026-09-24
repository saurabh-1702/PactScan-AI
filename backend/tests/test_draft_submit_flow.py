"""Phase 6b — drafting is separate from submitting. Suggest (and Ask) only
DRAFT; the requester previews, optionally edits, then submits. Three texts can
exist for one suggestion — AI draft, the requester's edit, the reviewer's edit —
and all of them are kept so the requester can see what changed. Mocked LLM +
embeddings + LlamaParse, in-memory graph + SQLite."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.agents.detect.graph_store import DEMO_TENANT, InMemoryGraphStore
from app.agents.detect.pipeline import ingest_and_detect
from app.agents.detect.seed_data import seed
from app.api.approvals import get_store as approvals_get_store
from app.api.deps import CurrentUser, get_current_user
from app.api.my_drafts import get_store as drafts_get_store
from app.api.suggest import get_store as suggest_get_store
from app.db.models import DocumentVersion, Notification
from app.db.postgres_client import get_db
from app.main import app
from tests.conftest import _CANNED_DOCS, _FakeLLM, _fake_embedding_vector

REQUESTER = CurrentUser(user_id="usr_requester", tenant_id=DEMO_TENANT, role="end_user")
OTHER_END_USER = CurrentUser(user_id="usr_other", tenant_id=DEMO_TENANT, role="end_user")
REVIEWER = CurrentUser(user_id="usr_reviewer", tenant_id=DEMO_TENANT, role="reviewer")


@pytest.fixture
def world(monkeypatch, fixture_pdf, db_session):
    fake = _FakeLLM()
    monkeypatch.setattr("app.llm.client.generate_structured", fake.generate_structured)
    monkeypatch.setattr("app.llm.client.generate_text", fake.generate_text)

    async def _embed(text):
        return _fake_embedding_vector(text)

    monkeypatch.setattr("app.llm.client.generate_embedding", _embed)
    monkeypatch.setattr(
        "app.agents.detect.ingest.parse_document", lambda p: _CANNED_DOCS[Path(p).name]()
    )

    store = InMemoryGraphStore()
    seed(store)
    report = asyncio.run(
        ingest_and_detect(
            store,
            fixture_pdf("contract_a_conflict.pdf"),
            "contract_a_conflict.pdf",
            contract_id="ct_draft_flow",
            db=db_session,
            uploaded_by_user_id=REQUESTER.user_id,
        )
    )
    finding = next(f for f in report.findings if len(f.override_chain) >= 2)

    def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    for getter in (suggest_get_store, drafts_get_store, approvals_get_store):
        app.dependency_overrides[getter] = lambda: store
    try:
        yield {
            "client": TestClient(app),
            "db": db_session,
            "store": store,
            "finding_id": finding.finding_id,
        }
    finally:
        app.dependency_overrides.clear()


def _as(user: CurrentUser):
    app.dependency_overrides[get_current_user] = lambda: user


def _draft(world) -> dict:
    _as(REQUESTER)
    resp = world["client"].post(f"/api/suggest/from-finding/{world['finding_id']}")
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_suggesting_only_drafts_it_is_not_queued_for_review(world):
    client = world["client"]
    draft = _draft(world)
    assert draft["approval_id"] is None

    _as(REVIEWER)
    assert client.get("/api/approvals").json() == []  # nothing in the reviewer's queue yet

    _as(REQUESTER)
    mine = client.get("/api/my-drafts").json()
    assert [d["suggestion_id"] for d in mine] == [draft["suggestion_id"]]
    assert mine[0]["status"] == "draft"
    assert mine[0]["ai_draft_text"] == draft["proposed_text"]


def test_submitting_the_ai_draft_as_is_queues_it_unedited(world):
    client = world["client"]
    draft = _draft(world)

    resp = client.post(f"/api/my-drafts/{draft['suggestion_id']}/submit", json={})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["requester_edited_text"] is None

    _as(REVIEWER)
    queue = client.get("/api/approvals").json()
    assert len(queue) == 1
    assert queue[0]["proposed_text"] == draft["proposed_text"]
    assert queue[0]["requested_by_user_id"] == REQUESTER.user_id


def test_submitting_an_edited_version_keeps_the_ai_text_separately(world):
    client = world["client"]
    draft = _draft(world)
    my_wording = "Liability is capped at twelve (12) months' fees, and any change needs a signed amendment."

    resp = client.post(
        f"/api/my-drafts/{draft['suggestion_id']}/submit", json={"edited_text": my_wording}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["requester_edited_text"] == my_wording
    assert resp.json()["ai_draft_text"] == draft["proposed_text"]  # AI text never overwritten

    _as(REVIEWER)
    item = client.get("/api/approvals").json()[0]
    assert item["proposed_text"] == my_wording  # what the reviewer is asked to decide on
    assert item["ai_draft_text"] == draft["proposed_text"]
    assert item["requester_edited_text"] == my_wording


def test_submitting_text_identical_to_the_ai_draft_is_not_recorded_as_an_edit(world):
    client = world["client"]
    draft = _draft(world)
    resp = client.post(
        f"/api/my-drafts/{draft['suggestion_id']}/submit",
        json={"edited_text": draft["proposed_text"]},
    )
    assert resp.json()["requester_edited_text"] is None


def test_a_draft_can_only_be_submitted_once(world):
    client = world["client"]
    draft = _draft(world)
    assert client.post(f"/api/my-drafts/{draft['suggestion_id']}/submit", json={}).status_code == 200
    assert client.post(f"/api/my-drafts/{draft['suggestion_id']}/submit", json={}).status_code == 409


def test_nobody_else_can_see_or_submit_my_draft(world):
    client = world["client"]
    draft = _draft(world)

    _as(OTHER_END_USER)
    assert client.get("/api/my-drafts").json() == []
    assert client.get(f"/api/my-drafts/{draft['suggestion_id']}").status_code == 404
    assert client.post(f"/api/my-drafts/{draft['suggestion_id']}/submit", json={}).status_code == 404


def test_approving_writes_the_requesters_edit_not_the_ai_text(world):
    client, db = world["client"], world["db"]
    draft = _draft(world)
    my_wording = "REQUESTER WORDING: liability capped at twelve months' fees."
    client.post(f"/api/my-drafts/{draft['suggestion_id']}/submit", json={"edited_text": my_wording})

    _as(REVIEWER)
    approval_id = client.get("/api/approvals").json()[0]["id"]
    resp = client.post(f"/api/approvals/{approval_id}/decide", json={"decision": "approved"})
    assert resp.status_code == 200, resp.text

    v2 = db.query(DocumentVersion).filter_by(contract_id="ct_draft_flow", version_number=2).one()
    text = "\n".join(p.text for p in Document(v2.file_path).paragraphs)
    assert my_wording in text
    assert draft["proposed_text"] not in text

    # approved without a reviewer edit -> the plain "approved and applied" message
    note = db.query(Notification).filter_by(recipient_user_id=REQUESTER.user_id).one()
    assert "approved and applied" in note.message


def test_the_requester_sees_all_three_texts_after_a_reviewer_edit(world):
    client, db = world["client"], world["db"]
    draft = _draft(world)
    my_wording = "REQUESTER WORDING v1."
    reviewer_wording = "REVIEWER WORDING, different from both."
    client.post(f"/api/my-drafts/{draft['suggestion_id']}/submit", json={"edited_text": my_wording})

    _as(REVIEWER)
    approval_id = client.get("/api/approvals").json()[0]["id"]
    client.post(
        f"/api/approvals/{approval_id}/decide",
        json={"decision": "approved", "edited_text": reviewer_wording, "note": "tightened"},
    )

    _as(REQUESTER)
    item = client.get(f"/api/my-drafts/{draft['suggestion_id']}").json()
    assert item["status"] == "approved"
    assert item["ai_draft_text"] == draft["proposed_text"]
    assert item["requester_edited_text"] == my_wording
    assert item["reviewer_edited_text"] == reviewer_wording
    assert item["reviewer_note"] == "tightened"
    assert item["document_version_id"] is not None

    # the reviewer changed what the requester submitted -> the "edited" message
    note = db.query(Notification).filter_by(recipient_user_id=REQUESTER.user_id).one()
    assert "wrote their own edit" in note.message
