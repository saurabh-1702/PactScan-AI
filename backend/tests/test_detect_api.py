"""Detect API tests (POST upload + GET idempotency), mocked LLM + LlamaParse."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.detect.graph_store import InMemoryGraphStore
from app.agents.detect.seed_data import seed
from app.api.detect import get_store
from app.db.postgres_client import get_db
from app.main import app
from tests.conftest import _CANNED_DOCS, _FakeLLM


@pytest.fixture
def api_client(monkeypatch, db_session):
    shared = InMemoryGraphStore()
    seed(shared)

    fake = _FakeLLM()
    monkeypatch.setattr("app.llm.client.generate_structured", fake.generate_structured)
    monkeypatch.setattr("app.llm.client.generate_text", fake.generate_text)
    monkeypatch.setattr(
        "app.agents.detect.ingest.parse_document",
        lambda p: _CANNED_DOCS[Path(p).name](),
    )
    app.dependency_overrides[get_store] = lambda: shared

    def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app), shared
    finally:
        app.dependency_overrides.clear()


def test_post_detect_returns_report(api_client, fixture_pdf):
    client, _ = api_client
    with open(fixture_pdf("contract_a_conflict.pdf"), "rb") as fh:
        resp = client.post(
            "/api/detect",
            files={"file": ("contract_a_conflict.pdf", fh, "application/pdf")},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["filename"] == "contract_a_conflict.pdf"
    assert body["total_findings"] == len(body["findings"]) >= 1


def test_post_detect_rejects_unsupported_type(api_client):
    client, _ = api_client
    resp = client.post(
        "/api/detect",
        files={"file": ("notes.md", b"# hello", "text/markdown")},
    )
    assert resp.status_code == 415


def test_get_detect_is_idempotent(api_client, fixture_pdf):
    client, _ = api_client
    with open(fixture_pdf("contract_b_regulation_gap.pdf"), "rb") as fh:
        resp = client.post(
            "/api/detect",
            files={"file": ("contract_b_regulation_gap.pdf", fh, "application/pdf")},
        )
    assert resp.status_code == 200, resp.text
    contract_id = resp.json()["contract_id"]

    first = client.get(f"/api/detect/{contract_id}")
    second = client.get(f"/api/detect/{contract_id}")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()["total_findings"] >= 2


def test_get_detect_unknown_contract_404(api_client):
    client, _ = api_client
    assert client.get("/api/detect/ct_does_not_exist").status_code == 404
