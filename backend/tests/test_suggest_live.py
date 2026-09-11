"""Live tests — real LlamaParse + real LLM (Groq/Gemini) + real Gemini embeddings
+ real Neo4j. Cost real quota. Run deliberately, once, after the mocked suite is
green:

    pytest -m live -v

Skipped automatically unless GEMINI_API_KEYS (needed for embeddings, regardless
of which provider leads text generation) and a real LLAMA_CLOUD_API_KEY are set.
"""

from __future__ import annotations

import pytest

from app.agents.detect.graph_store import Neo4jGraphStore
from app.agents.detect.pipeline import ingest_and_detect
from app.agents.detect.seed_data import seed
from app.agents.suggest.pipeline import suggest_from_finding, suggest_standalone
from app.config import settings

pytestmark = [pytest.mark.live, pytest.mark.asyncio]

_HAVE_KEYS = bool(settings.gemini_api_key_list) and settings.llama_cloud_api_key not in (
    "",
    "your_key_here",
)
_skip = pytest.mark.skipif(
    not _HAVE_KEYS, reason="GEMINI_API_KEYS (embeddings) / LLAMA_CLOUD_API_KEY not configured"
)


@_skip
async def test_live_suggest_from_finding_and_standalone(fixture_pdf, db_session):
    store = Neo4jGraphStore()
    seed(store)
    contract_id = "ct_live_suggest_phase2"
    store.wipe_contract(contract_id)

    report = await ingest_and_detect(
        store,
        fixture_pdf("contract_a_conflict.pdf"),
        "contract_a_conflict.pdf",
        contract_id=contract_id,
    )
    assert report.findings, "Detect produced no findings to suggest a fix for"
    finding = report.findings[0]

    result = await suggest_from_finding(store, db_session, finding.finding_id)
    assert result.proposed_text
    assert result.rationale
    assert 0 <= result.confidence <= 100

    clauses = store.get_clauses_for_contract(contract_id)
    other_clause = next(c for c in clauses if c.clause_id != finding.clause_id)
    standalone_result = await suggest_standalone(
        store, db_session, contract_id, other_clause.clause_id, "Tighten this clause's language."
    )
    assert standalone_result.finding_id is None
    assert standalone_result.proposed_text

    store.wipe_contract(contract_id)
