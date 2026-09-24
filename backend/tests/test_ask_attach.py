"""Phase 6b — attaching a contract in an Ask conversation. A real upload (full
Detect run, owned by the user) that becomes the chat's active document, so a
follow-up question can say "it" instead of naming the file. Mocked LLM +
embeddings + LlamaParse, in-memory graph + SQLite."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.detect.graph_store import DEMO_TENANT, InMemoryGraphStore
from app.agents.detect.pipeline import ingest_and_detect
from app.agents.detect.seed_data import seed
from app.api.ask import get_store as ask_get_store
from app.api.deps import CurrentUser, get_current_user
from app.db.models import DocumentVersion, Notification
from app.db.postgres_client import get_db
from app.main import app
from tests.conftest import _CANNED_DOCS, _FakeLLM, _fake_embedding_vector

ALICE = CurrentUser(user_id="usr_alice", tenant_id=DEMO_TENANT, role="end_user")
BOB = CurrentUser(user_id="usr_bob", tenant_id=DEMO_TENANT, role="end_user")


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

    def _db():
        yield db_session

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[ask_get_store] = lambda: store
    app.dependency_overrides[get_current_user] = lambda: ALICE
    try:
        yield {"client": TestClient(app), "store": store, "db": db_session, "pdf": fixture_pdf}
    finally:
        app.dependency_overrides.clear()


def _attach(world, name: str, session_id: str | None = None, user: CurrentUser = ALICE):
    app.dependency_overrides[get_current_user] = lambda: user
    with open(world["pdf"](name), "rb") as fh:
        return world["client"].post(
            "/api/ask/attach",
            files={"file": (name, fh, "application/pdf")},
            data={"session_id": session_id} if session_id else {},
        )


def _cited_documents(response_json: dict) -> set[str]:
    return {s["document_name"] for s in response_json["sources"] if s["page_number"] > 0}


def test_attaching_a_file_is_a_real_upload_owned_by_the_user(world):
    resp = _attach(world, "contract_a_conflict.pdf")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["type"] == "file_attached"
    assert body["contract_id"]

    store, db = world["store"], world["db"]
    mine = store.list_contracts(tenant_id=DEMO_TENANT, owner_user_id=ALICE.user_id)
    assert [c["contract_id"] for c in mine] == [body["contract_id"]]
    assert store.get_findings(body["contract_id"]), "Detect should have run on the attachment"
    assert db.query(DocumentVersion).filter_by(contract_id=body["contract_id"]).count() == 1
    assert db.query(Notification).filter_by(contract_owner_user_id=ALICE.user_id).count() >= 1


def test_a_follow_up_without_a_filename_is_answered_from_the_attached_file(world):
    client, store, db = world["client"], world["store"], world["db"]

    # a second contract of Alice's that is NOT attached — a portfolio search
    # would cite it too
    asyncio.run(
        ingest_and_detect(
            store, world["pdf"]("contract_b_regulation_gap.pdf"), "contract_b_regulation_gap.pdf",
            contract_id="ct_other", db=db, uploaded_by_user_id=ALICE.user_id,
        )
    )
    attached = _attach(world, "contract_a_conflict.pdf").json()

    followup = client.post(
        "/api/ask",
        json={"message": "What does it say about liability?", "session_id": attached["session_id"]},
    )
    assert followup.status_code == 200, followup.text
    assert followup.json()["type"] == "contract_answer"
    assert _cited_documents(followup.json()) == {"contract_a_conflict.pdf"}

    # the chat lists its active document, so the UI can show it
    sessions = client.get("/api/ask/sessions").json()
    mine = next(s for s in sessions if s["id"] == attached["session_id"])
    assert mine["active_contract_id"] == attached["contract_id"]
    assert mine["active_filename"] == "contract_a_conflict.pdf"

    # detach it -> the same question is a portfolio question again
    cleared = client.delete(f"/api/ask/sessions/{attached['session_id']}/active-document")
    assert cleared.status_code == 200
    again = client.post(
        "/api/ask",
        json={"message": "What does it say about liability?", "session_id": attached["session_id"]},
    )
    assert _cited_documents(again.json()) == {"contract_a_conflict.pdf", "contract_b_regulation_gap.pdf"}


def test_naming_a_document_still_beats_the_active_one(world):
    client, store, db = world["client"], world["store"], world["db"]
    asyncio.run(
        ingest_and_detect(
            store, world["pdf"]("contract_b_regulation_gap.pdf"), "contract_b_regulation_gap.pdf",
            contract_id="ct_other", db=db, uploaded_by_user_id=ALICE.user_id,
        )
    )
    attached = _attach(world, "contract_a_conflict.pdf").json()

    resp = client.post(
        "/api/ask",
        json={
            "message": "What does contract_b_regulation_gap.pdf say about consent?",
            "session_id": attached["session_id"],
        },
    )
    assert _cited_documents(resp.json()) == {"contract_b_regulation_gap.pdf"}


def test_someone_else_cannot_attach_into_my_conversation(world):
    attached = _attach(world, "contract_a_conflict.pdf").json()
    hijack = _attach(world, "contract_b_regulation_gap.pdf", session_id=attached["session_id"], user=BOB)
    assert hijack.status_code == 404


def test_unsupported_file_types_are_rejected(world):
    app.dependency_overrides[get_current_user] = lambda: ALICE
    resp = world["client"].post(
        "/api/ask/attach", files={"file": ("notes.md", b"# hello", "text/markdown")}
    )
    assert resp.status_code == 415
