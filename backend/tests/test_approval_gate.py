"""The human-approval gate (Phase 3) — the most important governance test in
the project: a redline can only ever be written into a document after an
explicit, logged 'approved' decision, and a 'rejected' decision must never
touch a file. Mocked LLM + embeddings + LlamaParse, in-memory graph + SQLite.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path

import pytest
from docx import Document
from fastapi.testclient import TestClient

from app.agents.detect.graph_store import InMemoryGraphStore
from app.agents.detect.pipeline import ingest_and_detect
from app.agents.detect.seed_data import seed
from app.agents.fix_and_learn.executor import (
    ExecutorNotAuthorizedError,
    apply_approved_redline,
)
from app.agents.suggest.pipeline import suggest_from_finding
from app.api.approvals import get_store as approvals_get_store
from app.db.models import Approval, AuditLog, DocumentVersion
from app.db.postgres_client import get_db
from app.main import app
from tests.conftest import _CANNED_DOCS, _FakeLLM, _fake_embedding_vector


def _hash_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


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
    """Detect -> Suggest on the real (fake-LLM) pipeline, producing:
    - a Neo4j-equivalent InMemoryGraphStore with contract_a's clauses/findings
    - a document_versions v1 (synthesized .docx, since the source is a PDF)
    - a redline_suggestion + its auto-created pending Approval
    """
    _wire_fakes(monkeypatch)
    store = InMemoryGraphStore()
    seed(store)

    async def _build():
        report = await ingest_and_detect(
            store,
            fixture_pdf("contract_a_conflict.pdf"),
            "contract_a_conflict.pdf",
            contract_id="ct_approval_test",
            db=db_session,
        )
        override_finding = next(f for f in report.findings if len(f.override_chain) >= 2)
        result = await suggest_from_finding(store, db_session, override_finding.finding_id)
        return override_finding, result

    finding, result = asyncio.run(_build())

    approval = (
        db_session.query(Approval)
        .filter(Approval.redline_suggestion_id == result.suggestion_id)
        .one()
    )
    assert approval.status == "pending"

    return {
        "store": store,
        "db": db_session,
        "finding": finding,
        "suggestion": result,
        "approval": approval,
        "contract_id": "ct_approval_test",
    }


# --------------------------------------------------------------------------- #
# 1. Executor guard — must refuse anything that isn't 'approved'
# --------------------------------------------------------------------------- #
def test_executor_refuses_non_approved_status(scenario):
    store, db, approval = scenario["store"], scenario["db"], scenario["approval"]
    assert approval.status == "pending"

    v1 = db.query(DocumentVersion).filter_by(contract_id=scenario["contract_id"]).one()
    before_hash = _hash_file(v1.file_path)
    versions_before = db.query(DocumentVersion).filter_by(contract_id=scenario["contract_id"]).count()

    with pytest.raises(ExecutorNotAuthorizedError):
        apply_approved_redline(db, store, approval.id)

    assert _hash_file(v1.file_path) == before_hash
    assert (
        db.query(DocumentVersion).filter_by(contract_id=scenario["contract_id"]).count()
        == versions_before
    )


# --------------------------------------------------------------------------- #
# API-driven tests (reject / approve) — share one dependency-overridden client
# --------------------------------------------------------------------------- #
@pytest.fixture
def api_client(scenario):
    store, db = scenario["store"], scenario["db"]

    def _override_get_db():
        yield db

    app.dependency_overrides[approvals_get_store] = lambda: store
    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app), scenario
    finally:
        app.dependency_overrides.clear()


def test_decide_rejected_never_touches_a_file(api_client):
    client, scenario = api_client
    db, approval = scenario["db"], scenario["approval"]
    v1 = db.query(DocumentVersion).filter_by(contract_id=scenario["contract_id"]).one()
    before_hash = _hash_file(v1.file_path)

    resp = client.post(f"/api/approvals/{approval.id}/decide", json={"decision": "rejected", "note": "not needed"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "rejected"

    assert _hash_file(v1.file_path) == before_hash
    assert db.query(DocumentVersion).filter_by(contract_id=scenario["contract_id"]).count() == 1

    decided = db.query(Approval).filter_by(id=approval.id).one()
    assert decided.status == "rejected"
    assert decided.decided_at is not None


def test_decide_approved_writes_new_version_and_audit_log(api_client):
    client, scenario = api_client
    db, approval, contract_id = scenario["db"], scenario["approval"], scenario["contract_id"]

    v1 = db.query(DocumentVersion).filter_by(contract_id=contract_id).one()
    v1_hash_before = _hash_file(v1.file_path)

    resp = client.post(f"/api/approvals/{approval.id}/decide", json={"decision": "approved"})
    assert resp.status_code == 200, resp.text
    assert resp.json()["status"] == "approved"

    versions = (
        db.query(DocumentVersion)
        .filter_by(contract_id=contract_id)
        .order_by(DocumentVersion.version_number)
        .all()
    )
    assert [v.version_number for v in versions] == [1, 2]
    v1_after, v2 = versions

    # original version untouched
    assert v1_after.id == v1.id
    assert v1_after.approval_id is None
    assert _hash_file(v1_after.file_path) == v1_hash_before

    # new version correctly attributed
    assert v2.approval_id == approval.id
    assert Path(v2.file_path).exists()

    audit_rows = db.query(AuditLog).filter_by(event_type="document_written").all()
    assert len(audit_rows) == 1
    details = json.loads(audit_rows[0].details)
    assert details["approval_id"] == approval.id
    assert details["new_version"] == 2

    # a decision can only be made once
    resp2 = client.post(f"/api/approvals/{approval.id}/decide", json={"decision": "approved"})
    assert resp2.status_code == 409


def test_decided_docx_contains_both_original_and_new_text(api_client):
    client, scenario = api_client
    db, approval, contract_id = scenario["db"], scenario["approval"], scenario["contract_id"]
    suggestion = scenario["suggestion"]
    original_clause_text = scenario["store"].get_clause_by_id(suggestion.clause_id).raw_text

    resp = client.post(f"/api/approvals/{approval.id}/decide", json={"decision": "approved"})
    assert resp.status_code == 200, resp.text

    v2 = (
        db.query(DocumentVersion)
        .filter_by(contract_id=contract_id, version_number=2)
        .one()
    )
    doc = Document(v2.file_path)
    full_text = "\n".join(p.text for p in doc.paragraphs)

    assert original_clause_text.strip() in full_text
    assert suggestion.proposed_text.strip() in full_text


def test_list_approvals_without_status_filter_returns_decided_items_too(api_client):
    """A decided approval must remain discoverable (and its document
    downloadable) via GET /api/approvals with no status filter — it must not
    only exist in the 'pending' view, which loses it the moment it's decided."""
    client, scenario = api_client
    approval = scenario["approval"]

    resp = client.post(f"/api/approvals/{approval.id}/decide", json={"decision": "approved"})
    assert resp.status_code == 200, resp.text

    pending = client.get("/api/approvals", params={"status": "pending"}).json()
    assert approval.id not in [a["id"] for a in pending]

    everything = client.get("/api/approvals").json()
    matching = [a for a in everything if a["id"] == approval.id]
    assert len(matching) == 1
    assert matching[0]["status"] == "approved"


def test_decide_approved_with_edited_text_writes_the_edit(api_client):
    client, scenario = api_client
    db, approval, contract_id = scenario["db"], scenario["approval"], scenario["contract_id"]
    edited = "EDITED BY REVIEWER: liability capped at Rupees 1,00,00,000 only."

    resp = client.post(
        f"/api/approvals/{approval.id}/decide",
        json={"decision": "approved", "edited_text": edited},
    )
    assert resp.status_code == 200, resp.text

    v2 = db.query(DocumentVersion).filter_by(contract_id=contract_id, version_number=2).one()
    doc = Document(v2.file_path)
    full_text = "\n".join(p.text for p in doc.paragraphs)
    assert edited in full_text
    assert scenario["suggestion"].proposed_text not in full_text
