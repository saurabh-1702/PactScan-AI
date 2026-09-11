"""Suggest agent tests (mocked LLM + embeddings + LlamaParse, in-memory graph
+ SQLite). No file on disk is ever touched by this phase."""

from __future__ import annotations

import pytest

from app.agents.detect.pipeline import ingest_and_detect
from app.agents.suggest.pipeline import suggest_from_finding, suggest_standalone
from app.db.models import RedlineSuggestion

pytestmark = pytest.mark.asyncio


async def _detect_contract_a(seeded_store, fixture_pdf):
    return await ingest_and_detect(
        seeded_store, fixture_pdf("contract_a_conflict.pdf"), "contract_a_conflict.pdf"
    )


async def test_suggest_from_finding_addresses_liability_cap(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session
):
    report = await _detect_contract_a(seeded_store, fixture_pdf)
    override_finding = next(f for f in report.findings if len(f.override_chain) >= 2)

    result = await suggest_from_finding(seeded_store, db_session, override_finding.finding_id)

    assert result.finding_id == override_finding.finding_id
    assert result.clause_id == override_finding.clause_id
    assert 0 <= result.confidence <= 100
    assert "cap" in result.proposed_text.lower() or "liability" in result.proposed_text.lower()
    assert result.rationale

    row = db_session.query(RedlineSuggestion).filter_by(id=result.suggestion_id).one()
    assert row.clause_id == override_finding.clause_id
    assert row.finding_id == override_finding.finding_id


async def test_suggest_standalone_with_no_prior_finding(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session
):
    report = await _detect_contract_a(seeded_store, fixture_pdf)
    clauses = seeded_store.get_clauses_for_contract(report.contract_id)
    governing_law = next(c for c in clauses if c.clause_type.value == "GOVERNING_LAW")

    result = await suggest_standalone(
        seeded_store,
        db_session,
        report.contract_id,
        governing_law.clause_id,
        "Change the governing law and jurisdiction to Delaware, USA.",
    )

    assert result.finding_id is None
    assert result.clause_id == governing_law.clause_id
    assert result.contract_id == report.contract_id

    row = db_session.query(RedlineSuggestion).filter_by(id=result.suggestion_id).one()
    assert row.finding_id is None


async def test_adversarial_review_changes_confidence(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session
):
    report = await _detect_contract_a(seeded_store, fixture_pdf)
    override_finding = next(f for f in report.findings if len(f.override_chain) >= 2)

    result = await suggest_from_finding(seeded_store, db_session, override_finding.finding_id)

    assert result.contrarian is not None
    assert result.judge is not None
    assert result.negotiation is not None
    # the fake judge downgrades the fake draft's 80 -> 60
    assert result.confidence == result.judge.final_confidence
    assert result.judge.final_confidence != 80


async def test_dismissed_verdict_is_persisted_not_dropped(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session, monkeypatch
):
    """A 'dismissed' Judge verdict must still show up in the result/DB row —
    never silently deleted."""
    from app.models.redline import JudgeVerdict

    async def _dismissing_judge(ctx, original_confidence, contrarian):
        return JudgeVerdict(
            verdict="dismissed",
            final_confidence=5,
            reasoning="The counterparty's cross-reference fully addresses the concern.",
        )

    monkeypatch.setattr("app.agents.suggest.pipeline.run_judge", _dismissing_judge)

    report = await _detect_contract_a(seeded_store, fixture_pdf)
    override_finding = next(f for f in report.findings if len(f.override_chain) >= 2)
    result = await suggest_from_finding(seeded_store, db_session, override_finding.finding_id)

    assert result.judge.verdict == "dismissed"
    row = db_session.query(RedlineSuggestion).filter_by(id=result.suggestion_id).one()
    assert row.judge_json and "dismissed" in row.judge_json


