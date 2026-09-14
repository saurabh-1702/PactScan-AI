"""Phase 5 — per-user draft rate limiting (Suggest API + Ask's edit-instruction
handoff). Both entry points are safe to leave open to every role (nothing ever
writes to a file without a separate reviewer/admin approval) — this only caps
how many drafts one user can queue per window. InMemoryRateLimiter throughout,
so this needs no Redis/Docker, matching the rest of the mocked suite.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.ask.pipeline import handle_ask
from app.agents.detect.graph_store import InMemoryGraphStore
from app.agents.detect.pipeline import ingest_and_detect
from app.agents.detect.seed_data import seed
from app.api.deps import get_current_user, get_rate_limiter
from app.api.suggest import get_store as suggest_get_store
from app.core.rate_limit import DraftRateLimitExceeded, InMemoryRateLimiter, check_draft_rate_limit
from app.db.postgres_client import get_db
from app.main import app
from app.models.ask import AskResponseType
from tests.conftest import _CANNED_DOCS, _FakeLLM, _fake_embedding_vector, default_current_user


def test_in_memory_rate_limiter_allows_then_blocks():
    limiter = InMemoryRateLimiter()
    for _ in range(3):
        allowed, retry_after = limiter.increment_and_check("k", limit=3, window_seconds=60)
        assert allowed is True
        assert retry_after == 0

    blocked, retry_after = limiter.increment_and_check("k", limit=3, window_seconds=60)
    assert blocked is False
    assert retry_after > 0


def test_check_draft_rate_limit_raises_with_retry_after():
    limiter = InMemoryRateLimiter()
    check_draft_rate_limit("user_x", limiter)  # 1st call, within default limit of 10

    for _ in range(20):
        try:
            check_draft_rate_limit("user_x", limiter)
        except DraftRateLimitExceeded as exc:
            assert exc.retry_after_seconds > 0
            return
    pytest.fail("expected DraftRateLimitExceeded to be raised within 20 more calls")


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


def test_suggest_standalone_429_after_limit_via_api(populated_store_and_db, monkeypatch):
    shared, db = populated_store_and_db
    monkeypatch.setattr("app.config.settings.draft_rate_limit_max", 2)

    clauses = shared.get_clauses_for_contract("ct_test_a")
    governing_law = next(c for c in clauses if c.clause_type.value == "GOVERNING_LAW")

    def _override_get_db():
        yield db

    # One shared instance across requests — a fresh lambda-constructed limiter
    # per call would reset the counter to zero on every request.
    limiter = InMemoryRateLimiter()

    app.dependency_overrides[suggest_get_store] = lambda: shared
    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_current_user] = default_current_user
    app.dependency_overrides[get_rate_limiter] = lambda: limiter
    client = TestClient(app)
    try:
        body = {
            "contract_id": "ct_test_a",
            "clause_id": governing_law.clause_id,
            "change_request": "Change governing law to Delaware.",
        }
        first = client.post("/api/suggest/standalone", json=body)
        second = client.post("/api/suggest/standalone", json=body)
        third = client.post("/api/suggest/standalone", json=body)

        assert first.status_code == 200, first.text
        assert second.status_code == 200, second.text
        assert third.status_code == 429
        assert "Retry-After" in third.headers
    finally:
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_ask_edit_instruction_rate_limited(monkeypatch, fixture_pdf, db_session):
    monkeypatch.setattr("app.config.settings.draft_rate_limit_max", 1)
    limiter = InMemoryRateLimiter()
    # check_draft_rate_limit() resolves get_rate_limiter() via its OWN module's
    # globals at call time, not at import time — patching it there is what
    # actually affects app.agents.ask.pipeline's un-parameterized call.
    monkeypatch.setattr("app.core.rate_limit.get_rate_limiter", lambda: limiter)

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

    store = InMemoryGraphStore()
    seed(store)
    await ingest_and_detect(
        store,
        fixture_pdf("contract_a_conflict.pdf"),
        "contract_a_conflict.pdf",
        contract_id="ct_test_a",
        db=db_session,
    )

    message = "Edit contract_a_conflict to change the liability cap to 2 crore."
    first = await handle_ask(store, db_session, message, session_id=None, user_id="user_y")
    assert first.type == AskResponseType.EDIT_DRAFT, first.answer_text

    second = await handle_ask(store, db_session, message, session_id=None, user_id="user_y")
    assert second.type == AskResponseType.RATE_LIMITED, second.answer_text
