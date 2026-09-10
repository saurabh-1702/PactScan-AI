"""Detect agent behaviour tests (mocked LLM + LlamaParse, in-memory graph)."""

from __future__ import annotations

import pytest

from app.agents.detect.pipeline import ingest_and_detect
from app.models.clause import Severity

pytestmark = pytest.mark.asyncio


async def _detect(store, fixture_pdf, name):
    return await ingest_and_detect(store, fixture_pdf(name), name)


# --------------------------------------------------------------------------- #
async def test_contract_a_detects_sow_overriding_msa(
    seeded_store, fake_llm, fake_parse, fixture_pdf
):
    report = await _detect(seeded_store, fixture_pdf, "contract_a_conflict.pdf")

    override_findings = [f for f in report.findings if len(f.override_chain) >= 2]
    assert override_findings, "expected a finding tracing the SOW->MSA override"
    f = override_findings[0]

    # override_chain points at real clauses spanning page 1 and page 2
    clauses = {c.clause_id: c for c in seeded_store.get_clauses_for_contract(report.contract_id)}
    pages = {clauses[cid].page_number for cid in f.override_chain if cid in clauses}
    assert pages == {1, 2}
    assert "page 2" in f.explanation.lower()
    assert f.severity == Severity.MEDIUM


async def test_contract_b_two_high_findings_dpdp_and_gdpr(
    seeded_store, fake_llm, fake_parse, fixture_pdf
):
    report = await _detect(seeded_store, fixture_pdf, "contract_b_regulation_gap.pdf")

    high = [f for f in report.findings if f.severity == Severity.HIGH]
    rules = " ".join(f.rule_or_regulation_violated for f in high)
    assert any("Section 9" in f.rule_or_regulation_violated for f in high), rules
    assert any("Article 8" in f.rule_or_regulation_violated for f in high), rules
    assert len(high) >= 2

    dpdp = next(f for f in high if "Section 9" in f.rule_or_regulation_violated)
    gdpr = next(f for f in high if "Article 8" in f.rule_or_regulation_violated)
    assert dpdp.clause_id == gdpr.clause_id  # same vague consent clause
    assert dpdp.page_number == 1


async def test_contract_c_clean_has_zero_findings(
    seeded_store, fake_llm, fake_parse, fixture_pdf
):
    report = await _detect(seeded_store, fixture_pdf, "contract_c_clean.pdf")
    assert report.total_findings == 0
    assert report.findings == []


async def test_every_finding_has_a_positive_integer_page_number(
    seeded_store, fake_llm, fake_parse, fixture_pdf
):
    for name in (
        "contract_a_conflict.pdf",
        "contract_b_regulation_gap.pdf",
        "contract_c_clean.pdf",
    ):
        store = seeded_store
        report = await _detect(store, fixture_pdf, name)
        for f in report.findings:
            assert isinstance(f.page_number, int)
            assert f.page_number >= 1


async def test_compliance_edges_written_for_regulation_findings(
    seeded_store, fake_llm, fake_parse, fixture_pdf
):
    report = await _detect(seeded_store, fixture_pdf, "contract_b_regulation_gap.pdf")
    edges = seeded_store.compliance_edges[("demo_tenant", report.contract_id)]
    rels = {(rel, target) for _, rel, target in edges}
    assert ("VIOLATES", "dpdp_s9") in rels
    assert ("VIOLATES", "gdpr_art8") in rels
