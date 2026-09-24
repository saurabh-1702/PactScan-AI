"""Endpoints added for the frontend redesign: /api/auth/me, /api/contracts,
real job progress, the regulatory-update log, `decided_by`, and Ask source
excerpts. In-memory graph + SQLite, mocked LLM."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.ask.answer_generator import _excerpt_for
from app.agents.ask.ask_retriever import AskRetrievedItem
from app.agents.detect.graph_store import DEMO_TENANT, InMemoryGraphStore
from app.agents.detect.seed_data import seed
from app.api.approvals import get_store as approvals_get_store
from app.api.contracts import get_store as contracts_get_store
from app.api.deps import CurrentUser, get_current_user
from app.api.detect import get_store as detect_get_store
from app.api.horizon_scanning import get_store as horizon_get_store
from app.api.my_drafts import get_store as my_drafts_get_store
from app.core.progress import DETECT_STAGES, InMemoryProgressTracker, JobProgress
from app.db.models import Approval, DocumentVersion, RedlineSuggestion, Tenant, User
from app.db.postgres_client import get_db
from app.main import app
from app.models.ask import AskSource
from app.models.clause import ClauseType, ConfidenceLevel, ExtractedClause, Finding, Severity
from tests.conftest import _CANNED_DOCS, _FakeLLM

ALICE = CurrentUser(user_id="usr_alice", tenant_id=DEMO_TENANT, role="end_user")
BOB = CurrentUser(user_id="usr_bob", tenant_id=DEMO_TENANT, role="end_user")
REVIEWER = CurrentUser(user_id="usr_rev", tenant_id=DEMO_TENANT, role="reviewer")


def _finding(fid: str, clause_id: str, severity: Severity, rule: str = "rule") -> Finding:
    return Finding(
        finding_id=fid,
        clause_id=clause_id,
        clause_type=ClauseType.DATA_PROCESSING,
        page_number=1,
        section_header="S",
        severity=severity,
        rule_or_regulation_violated=rule,
        explanation="why",
        confidence=ConfidenceLevel.high,
    )


@pytest.fixture
def world(db_session):
    db = db_session
    db.add(Tenant(id=DEMO_TENANT, name="Demo Tenant"))
    for u, email, role in [
        (ALICE, "alice@x.test", "end_user"),
        (BOB, "bob@x.test", "end_user"),
        (REVIEWER, "rev@x.test", "reviewer"),
    ]:
        db.add(User(id=u.user_id, tenant_id=DEMO_TENANT, email=email, hashed_password="x", role=role))
    db.commit()

    store = InMemoryGraphStore()
    seed(store)
    for cid, fname, owner, clause_id, sev in [
        ("ct_alice", "alice.pdf", ALICE.user_id, "cl_alice", Severity.HIGH),
        ("ct_bob", "bob.pdf", BOB.user_id, "cl_bob", Severity.LOW),
    ]:
        store.upsert_contract(cid, fname, tenant_id=DEMO_TENANT, uploaded_by_user_id=owner)
        store.add_clause(
            ExtractedClause(
                clause_id=clause_id,
                contract_id=cid,
                clause_type=ClauseType.DATA_PROCESSING,
                page_number=1,
                section_header="S",
                raw_text=f"text of {fname}",
                confidence=ConfidenceLevel.high,
            ),
            tenant_id=DEMO_TENANT,
        )
        store.replace_findings(cid, [_finding(f"fnd_{cid}", clause_id, sev)], tenant_id=DEMO_TENANT)
    db.add(
        DocumentVersion(
            tenant_id=DEMO_TENANT, contract_id="ct_alice", version_number=1, file_path="x"
        )
    )
    db.add(
        DocumentVersion(
            tenant_id=DEMO_TENANT, contract_id="ct_alice", version_number=2, file_path="y"
        )
    )
    db.commit()

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    for getter in (
        contracts_get_store,
        detect_get_store,
        approvals_get_store,
        horizon_get_store,
        my_drafts_get_store,
    ):
        app.dependency_overrides[getter] = lambda: store
    try:
        yield {"store": store, "db": db, "client": TestClient(app)}
    finally:
        app.dependency_overrides.clear()


def _as(user: CurrentUser):
    app.dependency_overrides[get_current_user] = lambda: user


# ------------------------------------------------------------------ /me
def test_me_returns_email_role_and_tenant_name(world):
    _as(ALICE)
    body = world["client"].get("/api/auth/me").json()
    assert body == {
        "user_id": "usr_alice",
        "email": "alice@x.test",
        "role": "end_user",
        "tenant_id": DEMO_TENANT,
        "tenant_name": "Demo Tenant",
    }


def test_me_requires_a_token(world):
    app.dependency_overrides.pop(get_current_user, None)
    assert world["client"].get("/api/auth/me").status_code == 401


# ------------------------------------------------------------- /contracts
def test_contract_list_is_scoped_and_carries_counts(world):
    client = world["client"]

    _as(ALICE)
    rows = client.get("/api/contracts").json()
    assert [r["contract_id"] for r in rows] == ["ct_alice"]
    only = rows[0]
    assert only["filename"] == "alice.pdf"
    assert only["uploaded_by_email"] == "alice@x.test"
    assert (only["high"], only["medium"], only["low"], only["total_findings"]) == (1, 0, 0, 1)
    assert only["version_count"] == 2
    assert only["uploaded_at"]

    _as(REVIEWER)
    everyone = {r["contract_id"]: r for r in client.get("/api/contracts").json()}
    assert set(everyone) == {"ct_alice", "ct_bob"}
    assert everyone["ct_bob"]["low"] == 1
    assert everyone["ct_bob"]["version_count"] == 0


# ---------------------------------------------------------------- progress
def test_tracker_reports_stages_in_order_and_finishes():
    tracker = InMemoryProgressTracker()
    assert tracker.start("job_12345678", "u1", "t", "Scanning a.pdf", DETECT_STAGES)
    progress = JobProgress(tracker, "job_12345678")

    progress.advance("extract")
    job = tracker.get("job_12345678", "u1")
    status = {s["key"]: s["status"] for s in job["stages"]}
    assert status["parse"] == "done"
    assert status["extract"] == "active"
    assert status["graph"] == "pending"
    assert job["state"] == "running"

    progress.finish()
    job = tracker.get("job_12345678", "u1")
    assert job["state"] == "done"
    assert all(s["status"] == "done" for s in job["stages"])


def test_tracker_failure_marks_the_active_stage_failed():
    tracker = InMemoryProgressTracker()
    tracker.start("job_12345678", "u1", "t", "x", DETECT_STAGES)
    progress = JobProgress(tracker, "job_12345678")
    progress.advance("check")
    progress.fail("boom")
    job = tracker.get("job_12345678", "u1")
    assert job["state"] == "failed"
    assert job["error"] == "boom"
    assert {s["key"]: s["status"] for s in job["stages"]}["check"] == "failed"


def test_tracker_is_private_to_the_owner_and_cannot_be_hijacked():
    tracker = InMemoryProgressTracker()
    assert tracker.start("job_12345678", "u1", "t", "x", DETECT_STAGES)
    assert tracker.get("job_12345678", "u2") is None
    assert not tracker.start("job_12345678", "u2", "t", "y", DETECT_STAGES)
    assert tracker.get("job_12345678", "u1")["label"] == "x"


def test_active_listing_only_shows_the_users_running_jobs_and_drops_stale_ones():
    tracker = InMemoryProgressTracker()
    tracker.start("job_aaaaaaaa", "u1", "t", "a", DETECT_STAGES)
    tracker.start("job_bbbbbbbb", "u1", "t", "b", DETECT_STAGES)
    tracker.start("job_cccccccc", "u2", "t", "c", DETECT_STAGES)
    tracker.finish("job_bbbbbbbb")
    assert [j["job_id"] for j in tracker.list_active("u1")] == ["job_aaaaaaaa"]

    tracker._jobs["job_aaaaaaaa"]["updated_at"] = time.time() - 3600
    assert tracker.list_active("u1") == []


def test_null_progress_is_a_harmless_no_op():
    p = JobProgress()
    p.advance("parse")
    p.finish()
    p.fail("x")


def test_detect_upload_reports_real_progress_through_the_api(monkeypatch, world, fixture_pdf):
    fake = _FakeLLM()
    monkeypatch.setattr("app.llm.client.generate_structured", fake.generate_structured)
    monkeypatch.setattr("app.llm.client.generate_text", fake.generate_text)
    monkeypatch.setattr(
        "app.agents.detect.ingest.parse_document", lambda p: _CANNED_DOCS[Path(p).name]()
    )
    client = world["client"]
    _as(ALICE)

    with open(fixture_pdf("contract_a_conflict.pdf"), "rb") as fh:
        resp = client.post(
            "/api/detect",
            files={"file": ("contract_a_conflict.pdf", fh, "application/pdf")},
            data={"job_id": "job_test_0001"},
        )
    assert resp.status_code == 200, resp.text

    job = client.get("/api/progress/job_test_0001").json()
    assert job["state"] == "done"
    assert [s["key"] for s in job["stages"]] == [k for k, _ in DETECT_STAGES]
    assert all(s["status"] == "done" for s in job["stages"])
    assert "user_id" not in job

    assert client.get("/api/progress/active").json() == []

    _as(BOB)
    assert client.get("/api/progress/job_test_0001").status_code == 404


def test_a_malformed_job_id_is_ignored_rather_than_breaking_the_upload(monkeypatch, world, fixture_pdf):
    fake = _FakeLLM()
    monkeypatch.setattr("app.llm.client.generate_structured", fake.generate_structured)
    monkeypatch.setattr("app.llm.client.generate_text", fake.generate_text)
    monkeypatch.setattr(
        "app.agents.detect.ingest.parse_document", lambda p: _CANNED_DOCS[Path(p).name]()
    )
    _as(ALICE)
    with open(fixture_pdf("contract_a_conflict.pdf"), "rb") as fh:
        resp = world["client"].post(
            "/api/detect",
            files={"file": ("contract_a_conflict.pdf", fh, "application/pdf")},
            data={"job_id": "no spaces/allowed!"},
        )
    assert resp.status_code == 200


# ------------------------------------------------- regulatory-update log
def test_update_log_lists_amendments_first_with_their_affected_contracts(world):
    store, client = world["store"], world["client"]
    older = store.add_regulation_update("DPDP Act 2023 (India)", "older rule", "2026-01-01")
    newer = store.add_regulation_update("GDPR", "newer rule", "2026-09-01")
    label = f"{newer['regulation_name']} {newer['section']} (update {newer['effective_date']})"
    store.add_findings(
        "ct_bob", [_finding("fnd_h", "cl_bob", Severity.MEDIUM, rule=label)], tenant_id=DEMO_TENANT
    )

    _as(REVIEWER)
    rows = client.get("/api/horizon-scanning/updates").json()
    updates = [r for r in rows if r["kind"] == "update"]
    assert [u["id"] for u in updates] == [newer["id"], older["id"]]  # newest effective date first
    assert all(r["kind"] == "baseline" for r in rows[len(updates):])
    assert updates[0]["jurisdiction"] == "European Union"
    assert updates[1]["jurisdiction"] == "India"
    assert updates[0]["affected_contracts"] == [{"contract_id": "ct_bob", "filename": "bob.pdf"}]
    assert updates[1]["affected_contracts"] == []


def test_update_log_only_names_contracts_the_caller_may_see(world):
    store, client = world["store"], world["client"]
    upd = store.add_regulation_update("GDPR", "rule", "2026-09-01")
    label = f"{upd['regulation_name']} {upd['section']} (update {upd['effective_date']})"
    store.add_findings(
        "ct_bob", [_finding("fnd_h", "cl_bob", Severity.MEDIUM, rule=label)], tenant_id=DEMO_TENANT
    )

    _as(ALICE)  # Alice does not own ct_bob
    rows = client.get("/api/horizon-scanning/updates").json()
    mine = next(r for r in rows if r["id"] == upd["id"])
    assert mine["affected_contracts"] == []

    _as(BOB)
    rows = client.get("/api/horizon-scanning/updates").json()
    mine = next(r for r in rows if r["id"] == upd["id"])
    assert [c["contract_id"] for c in mine["affected_contracts"]] == ["ct_bob"]


def test_update_log_is_readable_by_every_role_but_trigger_stays_admin_only(world):
    client = world["client"]
    for user in (ALICE, REVIEWER):
        _as(user)
        assert client.get("/api/horizon-scanning/updates").status_code == 200
        resp = client.post(
            "/api/horizon-scanning/simulate-update",
            json={"regulation_name": "x", "new_clause_text": "y", "effective_date": "2026-01-01"},
        )
        assert resp.status_code == 403


# -------------------------------------------------------------- decided_by
def test_the_deciding_reviewers_email_is_recorded_and_shown(world):
    db, client = world["db"], world["client"]
    sg = RedlineSuggestion(
        tenant_id=DEMO_TENANT,
        requested_by_user_id=ALICE.user_id,
        finding_id="fnd_ct_alice",
        contract_id="ct_alice",
        clause_id="cl_alice",
        proposed_text="p",
        rationale="r",
        confidence=50,
    )
    db.add(sg)
    db.flush()
    approval = Approval(redline_suggestion_id=sg.id, status="pending")
    db.add(approval)
    db.commit()

    _as(REVIEWER)
    decided = client.post(
        f"/api/approvals/{approval.id}/decide", json={"decision": "rejected", "note": "no"}
    ).json()
    assert decided["decided_by_email"] == "rev@x.test"

    _as(ALICE)
    draft = client.get(f"/api/my-drafts/{sg.id}").json()
    assert draft["decided_by_email"] == "rev@x.test"
    assert draft["status"] == "rejected"


# ------------------------------------------------------------ ask excerpts
def test_source_excerpt_comes_from_the_retrieved_passage_on_that_page():
    items = [
        AskRetrievedItem("a.pdf", 1, "first page text"),
        AskRetrievedItem("a.pdf", 3, "Breach   notification\nwithin 72 hours."),
    ]
    got = _excerpt_for(AskSource(document_name="a.pdf", page_number=3), items)
    assert got == "Breach notification within 72 hours."


def test_source_excerpt_falls_back_to_the_document_and_is_truncated():
    items = [AskRetrievedItem("a.pdf", 1, "x" * 1000)]
    got = _excerpt_for(AskSource(document_name="a.pdf", page_number=9), items)
    assert got is not None and len(got) == 320 and got.endswith("…")
    assert _excerpt_for(AskSource(document_name="other.pdf", page_number=1), items) is None
