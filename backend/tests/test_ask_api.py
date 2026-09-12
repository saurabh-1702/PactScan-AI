"""Ask API tests — endpoint wiring + chat session listing/replay, and an
edit-instruction file-immutability check at the HTTP layer (mirrors Phase 3's
governance test). Mocked LLM + embeddings + LlamaParse, in-memory graph + SQLite."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.detect.graph_store import InMemoryGraphStore
from app.agents.detect.pipeline import ingest_and_detect
from app.agents.detect.seed_data import seed
from app.api.ask import get_store as ask_get_store
from app.db.postgres_client import get_db
from app.main import app
from tests.conftest import _CANNED_DOCS, _FakeLLM, _fake_embedding_vector


@pytest.fixture
def populated_store_and_db(monkeypatch, fixture_pdf, db_session):
    store = InMemoryGraphStore()
    seed(store)

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

    asyncio.run(
        ingest_and_detect(
            store,
            fixture_pdf("contract_a_conflict.pdf"),
            "contract_a_conflict.pdf",
            contract_id="ct_test_a",
            db=db_session,
        )
    )
    return store, db_session


@pytest.fixture
def api_client(populated_store_and_db):
    store, db = populated_store_and_db

    def _override_get_db():
        yield db

    app.dependency_overrides[ask_get_store] = lambda: store
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app), store, db
    finally:
        app.dependency_overrides.clear()


def test_ask_endpoint_and_session_listing_and_replay(api_client):
    client, _store, _db = api_client

    resp1 = client.post("/api/ask", json={"message": "What is the DPDP Act?"})
    assert resp1.status_code == 200, resp1.text
    body1 = resp1.json()
    assert body1["type"] == "general_info"
    session_id = body1["session_id"]
    assert session_id

    resp2 = client.post(
        "/api/ask", json={"message": "What's the weather today?", "session_id": session_id}
    )
    assert resp2.status_code == 200, resp2.text
    assert resp2.json()["session_id"] == session_id  # continued the same conversation

    sessions = client.get("/api/ask/sessions").json()
    assert any(s["id"] == session_id for s in sessions)
    this_session = next(s for s in sessions if s["id"] == session_id)
    assert this_session["message_count"] == 4  # 2 user + 2 assistant

    messages = client.get(f"/api/ask/sessions/{session_id}/messages").json()
    assert [m["role"] for m in messages] == ["user", "assistant", "user", "assistant"]
    assert messages[0]["content"] == "What is the DPDP Act?"


def test_ask_sessions_unknown_id_404(api_client):
    client, _store, _db = api_client
    resp = client.get("/api/ask/sessions/cs_does_not_exist/messages")
    assert resp.status_code == 404


def test_ask_edit_instruction_via_api_never_modifies_a_file(api_client):
    client, store, db = api_client
    from app.db.models import DocumentVersion

    v1 = db.query(DocumentVersion).filter_by(contract_id="ct_test_a").one()
    before_hash = hashlib.sha256(Path(v1.file_path).read_bytes()).hexdigest()

    resp = client.post(
        "/api/ask",
        json={"message": "Edit contract_a_conflict to change the liability cap to 2 crore."},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["type"] == "edit_draft"
    assert body["suggestion_id"] is not None
    assert body["approval_id"] is not None

    assert hashlib.sha256(Path(v1.file_path).read_bytes()).hexdigest() == before_hash
    assert db.query(DocumentVersion).filter_by(contract_id="ct_test_a").count() == 1
