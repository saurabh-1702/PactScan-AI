"""Phase 6 — Horizon-Scanning (simulated regulation updates re-diffed against
already-signed contracts) and Document Restore (reverting to a prior version
through the same human-approval gate as any other edit). Mocked LLM +
embeddings, in-memory graph + SQLite — no Docker needed.
"""

from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.agents.detect.graph_store import DEMO_TENANT, InMemoryGraphStore
from app.agents.fix_and_learn.document_store import ensure_initial_version, synthesize_docx_bytes
from app.agents.horizon_scanning.regulation_writer import add_regulation_update
from app.agents.horizon_scanning.rediff import rediff_regulation_update
from app.agents.restore.executor import apply_approved_restore
from app.agents.restore.restore_agent import RestoreInputError, create_restore_request
from app.api.deps import CurrentUser, get_current_user
from app.db.models import AuditLog, DocumentVersion, Notification, RestoreRequest
from app.db.postgres_client import get_db
from app.main import app
from app.models.clause import ClauseType, ConfidenceLevel, ExtractedClause, Finding, Severity
from app.models.clause import NLILabel, NLIResult

CT_AFFECTED = "ct_hzs_affected"
CT_CLEAN = "ct_hzs_clean"


# --------------------------------------------------------------------------- #
# Horizon-Scanning
# --------------------------------------------------------------------------- #
@pytest.fixture
def hzs_store():
    """Two contracts, hand-picked embeddings so similarity is fully
    deterministic (not the shared hash-based fake, which can't guarantee one
    contract scores above threshold and the other below it)."""
    store = InMemoryGraphStore()

    store.upsert_contract(CT_AFFECTED, "affected.pdf", tenant_id=DEMO_TENANT)
    affected_clause = ExtractedClause(
        clause_id="cl_affected",
        contract_id=CT_AFFECTED,
        clause_type=ClauseType.DATA_PROCESSING,
        page_number=1,
        section_header="Consent",
        raw_text="The Vendor may process data on general consent with no special child provisions.",
        confidence=ConfidenceLevel.high,
    )
    store.add_clause(affected_clause, tenant_id=DEMO_TENANT)
    store.set_clause_embedding("cl_affected", [1.0, 0.0], tenant_id=DEMO_TENANT)
    # a pre-existing Detect finding, to prove Horizon-Scanning is ADDITIVE
    store.replace_findings(
        CT_AFFECTED,
        [
            Finding(
                finding_id="fnd_preexisting",
                clause_id="cl_affected",
                clause_type=ClauseType.DATA_PROCESSING,
                page_number=1,
                section_header="Consent",
                severity=Severity.LOW,
                rule_or_regulation_violated="pre-existing Detect finding",
                explanation="seeded before the horizon scan runs",
                confidence=ConfidenceLevel.high,
            )
        ],
        tenant_id=DEMO_TENANT,
    )

    store.upsert_contract(CT_CLEAN, "contract_c_clean.pdf", tenant_id=DEMO_TENANT)
    clean_clause = ExtractedClause(
        clause_id="cl_clean",
        contract_id=CT_CLEAN,
        clause_type=ClauseType.GOVERNING_LAW,
        page_number=1,
        section_header="Governing Law",
        raw_text="This Agreement is governed by the laws of India.",
        confidence=ConfidenceLevel.high,
    )
    store.add_clause(clean_clause, tenant_id=DEMO_TENANT)
    store.set_clause_embedding("cl_clean", [0.0, 1.0], tenant_id=DEMO_TENANT)  # orthogonal -> similarity 0

    return store


@pytest.fixture
def wire_horizon_fakes(monkeypatch):
    async def _embed(text: str) -> list[float]:
        # only the new regulation clause's text ever gets embedded live in
        # this flow (existing clauses already have their embeddings set above)
        return [1.0, 0.0]

    monkeypatch.setattr("app.llm.client.generate_embedding", _embed)

    async def _classify(prompt, schema, system_prompt=None):
        assert schema is NLIResult
        return NLIResult(
            label=NLILabel.CONTRADICTS,
            explanation="This clause does not require verifiable parental consent for children's data.",
            confidence=ConfidenceLevel.high,
        )

    monkeypatch.setattr("app.llm.client.generate_structured", _classify)


@pytest.mark.asyncio
async def test_simulate_update_flags_the_genuinely_affected_contract_only(
    hzs_store, wire_horizon_fakes, db_session
):
    new_clause = add_regulation_update(
        hzs_store,
        "DPDP Act 2023 (India)",
        "Data Fiduciaries must obtain verifiable parental consent before processing a child's data.",
        "2026-01-01",
    )
    summary = await rediff_regulation_update(hzs_store, db_session, new_clause, tenant_id=DEMO_TENANT)

    assert summary["contracts_flagged"] == 1
    assert summary["details"][0]["contract_id"] == CT_AFFECTED
    assert summary["findings_created"] == 1

    # additive — the pre-existing Detect finding must still be there
    affected_findings = hzs_store.get_findings(CT_AFFECTED)
    assert {f.finding_id for f in affected_findings} == {"fnd_preexisting", *summary["details"][0]["new_finding_ids"]}

    # contract_c_clean must never be flagged — its clause is topically unrelated
    assert hzs_store.get_findings(CT_CLEAN) == []


@pytest.mark.asyncio
async def test_horizon_scanning_finding_notifies_via_the_same_code_path_as_detect(
    hzs_store, wire_horizon_fakes, db_session
):
    new_clause = add_regulation_update(
        hzs_store, "DPDP Act 2023 (India)", "New mandatory child-consent requirement.", "2026-01-01"
    )
    summary = await rediff_regulation_update(hzs_store, db_session, new_clause, tenant_id=DEMO_TENANT)
    new_finding_id = summary["details"][0]["new_finding_ids"][0]

    notes = db_session.query(Notification).filter(Notification.finding_id == new_finding_id).all()
    assert len(notes) == 1
    assert notes[0].kind == "new_finding"  # exactly Detect's own notification kind, not a special one
    assert notes[0].recipient_user_id is None  # broadcast tenant-wide, same as a Detect finding


@pytest.mark.asyncio
async def test_rerunning_the_same_simulated_update_is_idempotent(hzs_store, wire_horizon_fakes, db_session):
    new_clause = add_regulation_update(
        hzs_store, "DPDP Act 2023 (India)", "New mandatory child-consent requirement.", "2026-01-01"
    )
    first = await rediff_regulation_update(hzs_store, db_session, new_clause, tenant_id=DEMO_TENANT)
    second = await rediff_regulation_update(hzs_store, db_session, new_clause, tenant_id=DEMO_TENANT)

    assert first["findings_created"] == 1
    assert second["findings_created"] == 0  # already-created findings are skipped, not duplicated
    assert len(hzs_store.get_findings(CT_AFFECTED)) == 2  # preexisting + the one horizon finding, not 3


# --------------------------------------------------------------------------- #
# Restore
# --------------------------------------------------------------------------- #
def _hash_file(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@pytest.fixture
def restore_scenario(db_session):
    clause = ExtractedClause(
        clause_id="cl_r1",
        contract_id="ct_restore_test",
        clause_type=ClauseType.GOVERNING_LAW,
        page_number=1,
        section_header="Governing Law",
        raw_text="Original text.",
        confidence=ConfidenceLevel.high,
    )
    ensure_initial_version(
        db_session, DEMO_TENANT, "ct_restore_test", "contract.docx",
        synthesize_docx_bytes([clause]), [clause],
    )
    v1 = db_session.query(DocumentVersion).filter_by(contract_id="ct_restore_test").one()

    # a v2, simulating a since-approved (and since regretted) edit
    v2_clause = ExtractedClause(**{**clause.model_dump(), "raw_text": "Edited (bad) text."})
    v2_path = Path(v1.file_path).parent / "v2.docx"
    v2_path.write_bytes(synthesize_docx_bytes([v2_clause]))
    v2 = DocumentVersion(
        tenant_id=DEMO_TENANT, contract_id="ct_restore_test", version_number=2, file_path=str(v2_path)
    )
    db_session.add(v2)
    db_session.commit()
    db_session.refresh(v2)

    return {"db": db_session, "v1": v1, "v2": v2}


def test_restore_request_with_empty_reason_is_rejected(restore_scenario):
    db, v1 = restore_scenario["db"], restore_scenario["v1"]
    with pytest.raises(RestoreInputError):
        create_restore_request(db, "ct_restore_test", v1.id, "usr_requester", "   ")


def test_end_user_can_request_but_not_decide(restore_scenario):
    """Role-gating itself is exercised at the HTTP layer (require_role, same
    as approvals) — this proves the AGENT-layer function has no opinion on
    role at all, i.e. any authenticated caller may create a request."""
    db, v1 = restore_scenario["db"], restore_scenario["v1"]
    request = create_restore_request(db, "ct_restore_test", v1.id, "usr_end_user", "Reverting a bad edit.")
    assert request.status == "pending"
    assert request.requested_by_user_id == "usr_end_user"


def test_end_user_403_reviewer_200_on_decide_restore_via_api(restore_scenario):
    """The exit-criteria test: an end_user-role JWT can create a restore
    request over HTTP but gets 403 attempting to decide it — the exact same
    require_role(["reviewer", "admin"]) gate as approvals."""
    db, v1 = restore_scenario["db"], restore_scenario["v1"]
    request = create_restore_request(db, "ct_restore_test", v1.id, "usr_end_user", "Reverting a bad edit.")

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    client = TestClient(app)
    try:
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id="usr_end_user", tenant_id=DEMO_TENANT, role="end_user"
        )
        forbidden = client.post(
            f"/api/restore-requests/{request.id}/decide", json={"decision": "rejected"}
        )
        assert forbidden.status_code == 403

        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            user_id="usr_reviewer", tenant_id=DEMO_TENANT, role="reviewer"
        )
        allowed = client.post(
            f"/api/restore-requests/{request.id}/decide", json={"decision": "rejected"}
        )
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["status"] == "rejected"
    finally:
        app.dependency_overrides.clear()


def test_approving_a_restore_creates_a_new_version_and_leaves_history_intact(restore_scenario):
    db, v1, v2 = restore_scenario["db"], restore_scenario["v1"], restore_scenario["v2"]
    v1_hash_before, v2_hash_before = _hash_file(v1.file_path), _hash_file(v2.file_path)

    request = create_restore_request(db, "ct_restore_test", v1.id, "usr_requester", "Reverting to v1.")
    request.status = "approved"
    db.commit()

    new_version = apply_approved_restore(db, request.id, tenant_id=DEMO_TENANT)

    versions = (
        db.query(DocumentVersion)
        .filter_by(contract_id="ct_restore_test")
        .order_by(DocumentVersion.version_number)
        .all()
    )
    assert [v.version_number for v in versions] == [1, 2, 3]
    assert new_version.version_number == 3
    assert _hash_file(new_version.file_path) == v1_hash_before  # v3's content == v1's content
    # neither prior version was touched
    assert _hash_file(v1.file_path) == v1_hash_before
    assert _hash_file(v2.file_path) == v2_hash_before

    audit_rows = db.query(AuditLog).filter_by(event_type="document_restored").all()
    assert len(audit_rows) == 1


def test_abuse_flagging_after_two_approved_restores_in_window(restore_scenario):
    db = restore_scenario["db"]
    contract_id = "ct_restore_test"
    now = datetime.now(timezone.utc)

    for i in range(2):
        db.add(
            RestoreRequest(
                tenant_id=DEMO_TENANT,
                contract_id=contract_id,
                target_version_id=restore_scenario["v1"].id,
                requested_by_user_id="usr_requester",
                reason=f"prior restore {i}",
                status="approved",
                decided_at=now - timedelta(days=1),
            )
        )
    db.commit()

    # create_restore_request already runs the abuse check internally — no
    # need (and, since it's not idempotent, no correctness) to call it again.
    third = create_restore_request(db, contract_id, restore_scenario["v1"].id, "usr_requester", "third restore")

    assert third.abuse_flagged is True
    assert db.query(AuditLog).filter_by(event_type="restore_pattern_flagged").count() == 1


def test_abuse_flagging_not_triggered_below_threshold(restore_scenario):
    db = restore_scenario["db"]
    contract_id = "ct_restore_test"

    db.add(
        RestoreRequest(
            tenant_id=DEMO_TENANT,
            contract_id=contract_id,
            target_version_id=restore_scenario["v1"].id,
            requested_by_user_id="usr_requester",
            reason="one prior restore",
            status="approved",
            decided_at=datetime.now(timezone.utc) - timedelta(days=1),
        )
    )
    db.commit()

    second = create_restore_request(db, contract_id, restore_scenario["v1"].id, "usr_requester", "second restore")
    assert second.abuse_flagged is False
