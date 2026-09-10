"""Live tests — real Gemini + real LlamaParse. Cost real quota.

Run deliberately, once, after the mocked suite is green:

    pytest -m live -v

Skipped automatically unless GEMINI_API_KEYS and a real LLAMA_CLOUD_API_KEY are
present in backend\\.env.
"""

from __future__ import annotations

import pytest

from app.agents.detect.graph_store import InMemoryGraphStore
from app.agents.detect.pipeline import ingest_and_detect
from app.agents.detect.seed_data import seed
from app.config import settings

pytestmark = [pytest.mark.live, pytest.mark.asyncio]

_HAVE_KEYS = bool(settings.gemini_api_key_list) and settings.llama_cloud_api_key not in (
    "",
    "your_key_here",
)
_skip = pytest.mark.skipif(not _HAVE_KEYS, reason="GEMINI_API_KEYS / LLAMA_CLOUD_API_KEY not configured")


@_skip
async def test_live_contract_a_conflict(fixture_pdf):
    store = InMemoryGraphStore()
    seed(store)
    report = await ingest_and_detect(
        store, fixture_pdf("contract_a_conflict.pdf"), "contract_a_conflict.pdf"
    )
    assert any(len(f.override_chain) >= 2 for f in report.findings), report.model_dump()


@_skip
async def test_live_contract_b_regulation_gap(fixture_pdf):
    store = InMemoryGraphStore()
    seed(store)
    report = await ingest_and_detect(
        store, fixture_pdf("contract_b_regulation_gap.pdf"), "contract_b_regulation_gap.pdf"
    )
    highs = [f for f in report.findings if f.severity.value == "HIGH"]
    labels = " ".join(f.rule_or_regulation_violated for f in highs)
    assert "Section 9" in labels, labels
    assert "Article 8" in labels, labels


@_skip
async def test_live_contract_c_clean(fixture_pdf):
    store = InMemoryGraphStore()
    seed(store)
    report = await ingest_and_detect(
        store, fixture_pdf("contract_c_clean.pdf"), "contract_c_clean.pdf"
    )
    # a clean contract should be quiet; a couple of low-confidence findings from a
    # real model is acceptable (the mocked test asserts exactly zero).
    assert report.total_findings <= 3, report.model_dump()
    # nothing should be flagged against the children's-consent regulations,
    # since contract C explicitly excludes children's data
    labels = " ".join(f.rule_or_regulation_violated for f in report.findings)
    assert "Section 9" not in labels and "Article 8" not in labels, labels
