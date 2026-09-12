"""Suggest API tests, incl. the file-immutability guarantee — Suggest never
writes to a file. Mocked LLM + embeddings + LlamaParse, in-memory graph + SQLite."""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.detect.graph_store import InMemoryGraphStore
from app.agents.detect.pipeline import ingest_and_detect
from app.agents.detect.seed_data import seed
from app.api.deps import get_current_user
from app.api.suggest import get_store as suggest_get_store
from app.db.postgres_client import get_db
from app.main import app
from tests.conftest import _CANNED_DOCS, _FakeLLM, _fake_embedding_vector, default_current_user


def _hash_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
        )
    )
    return store, db_session


def test_suggest_endpoints_never_modify_files(populated_store_and_db, fixture_pdf):
    shared, db = populated_store_and_db

    def _override_get_db():
        yield db

    app.dependency_overrides[suggest_get_store] = lambda: shared
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = default_current_user

    client = TestClient(app)
    try:
        paths = [
            fixture_pdf(name)
            for name in (
                "contract_a_conflict.pdf",
                "contract_b_regulation_gap.pdf",
                "contract_c_clean.pdf",
            )
        ]
        before = {p: _hash_file(p) for p in paths}

        findings = shared.get_findings("ct_test_a")
        target_finding = next(f for f in findings if len(f.override_chain) >= 2)
        resp1 = client.post(f"/api/suggest/from-finding/{target_finding.finding_id}")
        assert resp1.status_code == 200, resp1.text
        assert resp1.json()["proposed_text"]

        clauses = shared.get_clauses_for_contract("ct_test_a")
        governing_law = next(c for c in clauses if c.clause_type.value == "GOVERNING_LAW")
        resp2 = client.post(
            "/api/suggest/standalone",
            json={
                "contract_id": "ct_test_a",
                "clause_id": governing_law.clause_id,
                "change_request": "Change governing law to Delaware.",
            },
        )
        assert resp2.status_code == 200, resp2.text
        assert resp2.json()["finding_id"] is None

        after = {p: _hash_file(p) for p in paths}
        assert before == after, "Suggest must never modify a file on disk"
    finally:
        app.dependency_overrides.clear()


def test_suggest_from_finding_unknown_id_404(populated_store_and_db):
    shared, db = populated_store_and_db

    def _override_get_db():
        yield db

    app.dependency_overrides[suggest_get_store] = lambda: shared
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = default_current_user
    client = TestClient(app)
    try:
        resp = client.post("/api/suggest/from-finding/fnd_does_not_exist")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.clear()
