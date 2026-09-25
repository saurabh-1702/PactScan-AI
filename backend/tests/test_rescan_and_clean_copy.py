"""Clean (changes-accepted) downloads and the re-scan of a contract's current
version. In-memory graph + SQLite; parsing/LLM steps are stubbed."""

from __future__ import annotations

import io
import json
from datetime import datetime, timedelta, timezone

import pytest
from docx import Document
from fastapi.testclient import TestClient
from sqlalchemy import Column, MetaData, String, Table, create_engine, inspect

from app.agents.detect import ingest
from app.agents.detect.graph_store import DEMO_TENANT, InMemoryGraphStore
from app.agents.detect.ingest import ParsedDocument, ParsedPage
from app.agents.fix_and_learn import executor as fl_executor
from app.agents.fix_and_learn.clean_copy import make_clean_docx
from app.agents.fix_and_learn.document_store import synthesize_docx_bytes
from app.agents.rescan import pipeline as rescan_pipeline
from app.api.approvals import get_store as approvals_get_store
from app.api.contracts import get_store as contracts_get_store
from app.api.deps import CurrentUser, get_current_user
from app.api.documents import get_store as documents_get_store
from app.api.my_drafts import get_store as drafts_get_store
from app.db.models import (
    Approval,
    AuditLog,
    DocumentVersion,
    Notification,
    RedlineSuggestion,
    RestoreRequest,
)
from app.db.postgres_client import get_db
from app.db.schema_upgrades import apply_schema_upgrades
from app.main import app
from app.models.clause import ClauseType, ConfidenceLevel, ExtractedClause, Finding, Severity

ALICE = CurrentUser(user_id="usr_alice", tenant_id=DEMO_TENANT, role="end_user")
BOB = CurrentUser(user_id="usr_bob", tenant_id=DEMO_TENANT, role="end_user")
REVIEWER = CurrentUser(user_id="usr_rev", tenant_id=DEMO_TENANT, role="reviewer")

OLD = "The Processor shall notify the Company of a breach within 30 days."
NEW = "The Processor shall notify the Company of a breach within 72 hours."


def _clause(cid: str, text: str = OLD, contract="ct_a") -> ExtractedClause:
    return ExtractedClause(
        clause_id=cid,
        contract_id=contract,
        clause_type=ClauseType.BREACH_NOTIFICATION,
        page_number=1,
        section_header="Breach",
        raw_text=text,
        confidence=ConfidenceLevel.high,
    )


def _finding(fid: str, clause_id: str) -> Finding:
    return Finding(
        finding_id=fid,
        clause_id=clause_id,
        clause_type=ClauseType.BREACH_NOTIFICATION,
        page_number=1,
        section_header="Breach",
        severity=Severity.MEDIUM,
        rule_or_regulation_violated="rule",
        explanation="why",
        confidence=ConfidenceLevel.high,
    )


def _paragraph_texts(docx_bytes: bytes) -> list[str]:
    return [p.text for p in Document(io.BytesIO(docx_bytes)).paragraphs]


def _redline_bytes(old: str, new: str) -> bytes:
    """A v1 with the Executor's own strike-through edit applied to it."""
    doc = Document(io.BytesIO(synthesize_docx_bytes([_clause("cl_1", old)])))
    assert fl_executor._apply_tracked_change(doc, old, new)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


# ------------------------------------------------------------------ clean copy
def test_clean_copy_keeps_only_the_new_wording_and_drops_all_markup():
    redline = _redline_bytes(OLD, NEW)
    assert OLD in " ".join(_paragraph_texts(redline))  # the redline still carries the old text

    clean = make_clean_docx(redline)
    texts = _paragraph_texts(clean)
    assert NEW in texts
    assert not any(OLD in t or "→" in t for t in texts)

    for p in Document(io.BytesIO(clean)).paragraphs:
        for run in p.runs:
            assert not run.font.strike
            assert run.font.underline in (None, False)


def test_clean_copy_of_an_unedited_document_is_the_same_text():
    original = synthesize_docx_bytes([_clause("cl_1"), _clause("cl_2", "Second clause text.")])
    assert _paragraph_texts(make_clean_docx(original)) == _paragraph_texts(original)


def test_a_second_edit_of_the_same_clause_cleans_to_the_latest_wording_only():
    once = _redline_bytes(OLD, NEW)
    doc = Document(io.BytesIO(once))
    assert fl_executor._apply_tracked_change(doc, OLD, "Latest wording.")
    buf = io.BytesIO()
    doc.save(buf)

    texts = _paragraph_texts(make_clean_docx(buf.getvalue()))
    assert "Latest wording." in texts
    assert not any(OLD in t or NEW in t for t in texts)


def test_the_synthesized_preamble_can_be_stripped_before_a_rescan():
    original = synthesize_docx_bytes([_clause("cl_1")])
    joined = " ".join(_paragraph_texts(original))
    assert "Reconstructed Contract" in joined and "was reconstructed" in joined

    stripped = " ".join(_paragraph_texts(make_clean_docx(original, strip_preamble=True)))
    assert "Reconstructed Contract" not in stripped and "was reconstructed" not in stripped
    assert OLD in stripped


# ---------------------------------------------------------------------- world
@pytest.fixture
def world(db_session, tmp_path):
    db = db_session
    store = InMemoryGraphStore()
    store.upsert_contract("ct_a", "a.pdf", tenant_id=DEMO_TENANT, uploaded_by_user_id=ALICE.user_id)
    store.add_clause(_clause("cl_old"), tenant_id=DEMO_TENANT)
    store.replace_findings("ct_a", [_finding("fnd_old", "cl_old")], tenant_id=DEMO_TENANT)

    def add_version(n: int, content: bytes, approval_id=None) -> DocumentVersion:
        path = tmp_path / f"v{n}.docx"
        path.write_bytes(content)
        v = DocumentVersion(
            tenant_id=DEMO_TENANT,
            contract_id="ct_a",
            version_number=n,
            file_path=str(path),
            approval_id=approval_id,
        )
        db.add(v)
        db.commit()
        return v

    add_version(1, synthesize_docx_bytes([_clause("cl_old")]))

    def _db():
        yield db

    app.dependency_overrides[get_db] = _db
    for getter in (contracts_get_store, documents_get_store, approvals_get_store, drafts_get_store):
        app.dependency_overrides[getter] = lambda: store
    try:
        yield {
            "store": store,
            "db": db,
            "client": TestClient(app),
            "add_version": add_version,
            "tmp": tmp_path,
        }
    finally:
        app.dependency_overrides.clear()


def _as(user: CurrentUser):
    app.dependency_overrides[get_current_user] = lambda: user


def _audit(db, event: str, **details):
    db.add(AuditLog(event_type=event, entity_id="ct_a", details=json.dumps(details)))
    db.commit()


# ------------------------------------------------------------ download format
def test_download_defaults_to_the_redline_and_clean_is_generated_on_request(world):
    v2 = world["add_version"](2, _redline_bytes(OLD, NEW), approval_id="apv_x")
    client = world["client"]
    _as(ALICE)

    redline = client.get(f"/api/documents/version/{v2.id}/download")
    assert redline.status_code == 200
    assert OLD in " ".join(_paragraph_texts(redline.content))

    clean = client.get(f"/api/documents/version/{v2.id}/download", params={"format": "clean"})
    assert clean.status_code == 200
    assert "_clean.docx" in clean.headers["content-disposition"]
    texts = _paragraph_texts(clean.content)
    assert NEW in texts and not any(OLD in t for t in texts)

    # the stored version itself is untouched
    assert OLD in " ".join(_paragraph_texts(open(v2.file_path, "rb").read()))
    assert client.get(f"/api/documents/version/{v2.id}/download", params={"format": "x"}).status_code == 422


def test_clean_download_respects_ownership(world):
    v1 = world["db"].query(DocumentVersion).first()
    _as(BOB)
    resp = world["client"].get(f"/api/documents/version/{v1.id}/download", params={"format": "clean"})
    assert resp.status_code == 404


# ------------------------------------------------------------------- scan info
def test_findings_describe_v1_until_something_changes_the_wording(world):
    _as(ALICE)
    info = world["client"].get("/api/contracts/ct_a/scan-info").json()
    assert (info["latest_version"], info["scanned_version"], info["stale"]) == (1, 1, False)
    assert info["can_rescan"] is True


def test_an_approved_edit_makes_the_findings_stale(world):
    world["add_version"](2, _redline_bytes(OLD, NEW), approval_id="apv_x")
    _as(ALICE)
    info = world["client"].get("/api/contracts/ct_a/scan-info").json()
    assert (info["latest_version"], info["scanned_version"], info["stale"]) == (2, 1, True)


def test_restoring_to_the_scanned_version_is_not_stale_but_restoring_an_edit_is(world):
    world["add_version"](2, _redline_bytes(OLD, NEW), approval_id="apv_x")
    world["add_version"](3, synthesize_docx_bytes([_clause("cl_old")]))  # a restore of v1
    _audit(world["db"], "document_restored", new_version=3, target_version_number=1)
    _as(ALICE)
    info = world["client"].get("/api/contracts/ct_a/scan-info").json()
    assert (info["latest_version"], info["stale"]) == (3, False)

    world["add_version"](4, _redline_bytes(OLD, NEW))  # a restore of v2
    _audit(world["db"], "document_restored", new_version=4, target_version_number=2)
    assert world["client"].get("/api/contracts/ct_a/scan-info").json()["stale"] is True


def test_someone_elses_contract_has_no_scan_info_or_rescan(world):
    _as(BOB)
    assert world["client"].get("/api/contracts/ct_a/scan-info").status_code == 404
    assert world["client"].post("/api/contracts/ct_a/rescan", json={}).status_code == 404


# ------------------------------------------------------------- rescan blockers
def _draft(db, status=None) -> RedlineSuggestion:
    sg = RedlineSuggestion(
        tenant_id=DEMO_TENANT,
        requested_by_user_id=ALICE.user_id,
        finding_id="fnd_old",
        contract_id="ct_a",
        clause_id="cl_old",
        original_clause_text=OLD,
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


@pytest.mark.parametrize("setup", ["pending_approval", "unsubmitted_draft", "pending_restore"])
def test_rescan_is_refused_while_anything_is_pending_against_the_contract(world, setup):
    db = world["db"]
    if setup == "pending_approval":
        _draft(db, "pending")
    elif setup == "unsubmitted_draft":
        _draft(db)
    else:
        v1 = db.query(DocumentVersion).first()
        db.add(
            RestoreRequest(
                tenant_id=DEMO_TENANT,
                contract_id="ct_a",
                target_version_id=v1.id,
                requested_by_user_id=ALICE.user_id,
                reason="r",
            )
        )
        db.commit()
    _as(ALICE)

    info = world["client"].get("/api/contracts/ct_a/scan-info").json()
    assert info["can_rescan"] is False
    resp = world["client"].post("/api/contracts/ct_a/rescan", json={})
    assert resp.status_code == 409
    assert "Decide, submit or delete" in resp.json()["detail"]
    assert [f.finding_id for f in world["store"].get_findings("ct_a")] == ["fnd_old"]  # untouched


def test_decided_drafts_do_not_block_a_rescan(world):
    _draft(world["db"], "approved")
    _draft(world["db"], "rejected")
    _as(ALICE)
    assert world["client"].get("/api/contracts/ct_a/scan-info").json()["can_rescan"] is True


# ---------------------------------------------------------------- rescan flow
@pytest.fixture
def stubbed_scan(monkeypatch, world):
    """Parsing and detection are stubbed; the graph/audit/notification behaviour
    around them is the real code under test."""
    calls = {"rediff": [], "run_detect": 0, "parsed_text": ""}

    def parse(path):
        text = "\n".join(p.text for p in Document(str(path)).paragraphs)
        calls["parsed_text"] = text
        return ParsedDocument(filename=path.name, pages=[ParsedPage(page_number=1, text=text)])

    async def extract(parsed, contract_id):
        return [_clause("cl_new", NEW, contract=contract_id)]

    async def detect(store, contract_id, tenant_id=DEMO_TENANT):
        calls["run_detect"] += 1
        f = [_finding("fnd_new", "cl_new")]
        store.replace_findings(contract_id, f, tenant_id=tenant_id)
        return f

    async def rediff(store, db, new_clause, tenant_id=DEMO_TENANT, only_contract_id=None, notify=True):
        calls["rediff"].append((new_clause["id"], only_contract_id, notify))
        return {"contracts_flagged": 0, "findings_created": 0, "details": []}

    monkeypatch.setattr(ingest, "parse_document", parse)
    monkeypatch.setattr(ingest, "extract_clauses", extract)
    monkeypatch.setattr(rescan_pipeline, "run_detect", detect)
    monkeypatch.setattr(rescan_pipeline, "rediff_regulation_update", rediff)
    return calls


def test_a_rescan_reads_the_clean_current_version_and_refreshes_the_findings(world, stubbed_scan):
    store, db, client = world["store"], world["db"], world["client"]
    world["add_version"](2, _redline_bytes(OLD, NEW), approval_id="apv_x")
    amendment = store.add_regulation_update("DPDP Act 2023 (India)", "New rule.", "2026-10-01")
    _as(ALICE)

    resp = client.post("/api/contracts/ct_a/rescan", json={})
    assert resp.status_code == 200, resp.text
    assert resp.json() == {
        "contract_id": "ct_a",
        "scanned_version": 2,
        "findings_before": 1,
        "findings_after": 1,
    }

    # it read the changes-accepted text, not the redline
    assert NEW in stubbed_scan["parsed_text"]
    assert OLD not in stubbed_scan["parsed_text"] and "→" not in stubbed_scan["parsed_text"]
    assert "Reconstructed Contract" not in stubbed_scan["parsed_text"]

    # old clauses/findings replaced; the contract itself (owner!) is kept
    assert store.get_clause_by_id("cl_old", tenant_id=DEMO_TENANT) is None
    assert store.get_clause_by_id("cl_new", tenant_id=DEMO_TENANT) is not None
    assert [f.finding_id for f in store.get_findings("ct_a")] == ["fnd_new"]
    owner = next(c for c in store.list_contracts(tenant_id=DEMO_TENANT) if c["contract_id"] == "ct_a")
    assert owner["uploaded_by_user_id"] == ALICE.user_id

    # every recorded regulation update was re-checked, for this contract only, quietly
    assert stubbed_scan["rediff"] == [(amendment["id"], "ct_a", False)]
    assert db.query(Notification).count() == 0

    # no new document version, and the findings now describe the current wording
    assert db.query(DocumentVersion).filter_by(contract_id="ct_a").count() == 2
    info = client.get("/api/contracts/ct_a/scan-info").json()
    assert (info["scanned_version"], info["stale"], info["incomplete"]) == (2, False, False)
    assert db.query(AuditLog).filter_by(event_type="contract_rescan_completed").count() == 1


def test_an_unreadable_document_changes_nothing(world, monkeypatch, stubbed_scan):
    async def nothing(parsed, contract_id):
        return []

    monkeypatch.setattr(ingest, "extract_clauses", nothing)
    _as(ALICE)

    resp = world["client"].post("/api/contracts/ct_a/rescan", json={})
    assert resp.status_code == 422
    assert [f.finding_id for f in world["store"].get_findings("ct_a")] == ["fnd_old"]
    assert world["store"].get_clause_by_id("cl_old", tenant_id=DEMO_TENANT) is not None
    info = world["client"].get("/api/contracts/ct_a/scan-info").json()
    assert info["incomplete"] is False and info["running"] is False


def test_a_failure_after_the_old_analysis_was_replaced_is_reported_and_retryable(
    world, monkeypatch, stubbed_scan
):
    async def boom(store, contract_id, tenant_id=DEMO_TENANT):
        raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(rescan_pipeline, "run_detect", boom)
    _as(ALICE)
    client = world["client"]

    assert client.post("/api/contracts/ct_a/rescan", json={}).status_code == 502
    info = client.get("/api/contracts/ct_a/scan-info").json()
    assert info["incomplete"] is True and info["running"] is False and info["can_rescan"] is True

    # retrying repairs it
    async def detect(store, contract_id, tenant_id=DEMO_TENANT):
        f = [_finding("fnd_new", "cl_new")]
        store.replace_findings(contract_id, f, tenant_id=tenant_id)
        return f

    monkeypatch.setattr(rescan_pipeline, "run_detect", detect)
    assert client.post("/api/contracts/ct_a/rescan", json={}).status_code == 200
    assert client.get("/api/contracts/ct_a/scan-info").json()["incomplete"] is False


def test_a_rescan_that_is_already_running_blocks_a_second_one(world, stubbed_scan):
    _audit(world["db"], "contract_rescan_started", version_number=1, by="usr_x")
    _as(ALICE)
    info = world["client"].get("/api/contracts/ct_a/scan-info").json()
    assert info["running"] is True and info["can_rescan"] is False
    assert world["client"].post("/api/contracts/ct_a/rescan", json={}).status_code == 409


def test_a_rescan_that_started_long_ago_and_never_finished_counts_as_failed(world, stubbed_scan):
    world["db"].add(
        AuditLog(
            event_type="contract_rescan_started",
            entity_id="ct_a",
            details=json.dumps({"version_number": 1}),
            created_at=datetime.now(timezone.utc) - timedelta(hours=2),
        )
    )
    world["db"].commit()
    _as(ALICE)
    info = world["client"].get("/api/contracts/ct_a/scan-info").json()
    assert info["running"] is False and info["incomplete"] is True


# ----------------------------------------------- history survives a re-scan
def test_a_decided_drafts_wording_survives_a_rescan_via_its_snapshot(world, stubbed_scan):
    db, client = world["db"], world["client"]
    with_snapshot = _draft(db, "approved")
    no_snapshot = _draft(db, "rejected")
    no_snapshot.original_clause_text = None
    db.commit()
    _as(ALICE)
    assert client.post("/api/contracts/ct_a/rescan", json={}).status_code == 200

    drafts = {d["suggestion_id"]: d for d in client.get("/api/my-drafts").json()}
    assert drafts[with_snapshot.id]["original_clause_text"] == OLD
    assert "no longer in the current scan" in drafts[no_snapshot.id]["original_clause_text"]

    _as(REVIEWER)
    approvals = {a["redline_suggestion_id"]: a for a in client.get("/api/approvals").json()}
    assert approvals[with_snapshot.id]["original_clause_text"] == OLD


def test_a_draft_whose_clause_was_replaced_cannot_be_submitted(world):
    sg = _draft(world["db"])
    world["store"].reset_contract_analysis("ct_a", tenant_id=DEMO_TENANT)
    _as(ALICE)
    resp = world["client"].post(f"/api/my-drafts/{sg.id}/submit", json={})
    assert resp.status_code == 409
    assert "re-scanned" in resp.json()["detail"]


# --------------------------------------------------- store + schema upgrades
def test_resetting_the_analysis_keeps_the_contract_but_drops_its_clauses_and_findings():
    store = InMemoryGraphStore()
    store.upsert_contract("ct_a", "a.pdf", uploaded_by_user_id="usr_alice")
    store.add_clause(_clause("cl_1"))
    store.replace_findings("ct_a", [_finding("fnd_1", "cl_1")])

    store.reset_contract_analysis("ct_a")

    assert store.get_clauses_for_contract("ct_a") == []
    assert store.get_findings("ct_a") == []
    kept = store.list_contracts()
    assert [(c["contract_id"], c["uploaded_by_user_id"]) for c in kept] == [("ct_a", "usr_alice")]


def test_schema_upgrade_adds_the_missing_column_once_and_leaves_data_alone():
    engine = create_engine("sqlite:///:memory:")
    meta = MetaData()
    Table("redline_suggestions", meta, Column("id", String, primary_key=True))
    meta.create_all(engine)
    with engine.begin() as conn:
        conn.exec_driver_sql("INSERT INTO redline_suggestions (id) VALUES ('sg_1')")

    assert apply_schema_upgrades(engine) == ["redline_suggestions.original_clause_text"]
    assert "original_clause_text" in {c["name"] for c in inspect(engine).get_columns("redline_suggestions")}
    assert apply_schema_upgrades(engine) == []  # idempotent
    with engine.connect() as conn:
        assert conn.exec_driver_sql("SELECT id, original_clause_text FROM redline_suggestions").all() == [
            ("sg_1", None)
        ]
