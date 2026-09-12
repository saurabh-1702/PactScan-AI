"""Live tests — real Groq/Gemini + real Gemini embeddings + real Neo4j/Postgres.
Cost real quota. Run deliberately, once, after the mocked suite is green:

    pytest -m live -v

Skipped automatically unless GEMINI_API_KEYS (needed for embeddings, regardless
of which provider leads text generation) and a real LLAMA_CLOUD_API_KEY are set.
"""

from __future__ import annotations

import pytest

from app.agents.ask.pipeline import handle_ask
from app.agents.detect.graph_store import Neo4jGraphStore
from app.agents.detect.pipeline import ingest_and_detect
from app.agents.detect.seed_data import seed
from app.config import settings
from app.models.ask import AskResponseType

pytestmark = [pytest.mark.live, pytest.mark.asyncio]

_HAVE_KEYS = bool(settings.gemini_api_key_list) and settings.llama_cloud_api_key not in (
    "",
    "your_key_here",
)
_skip = pytest.mark.skipif(
    not _HAVE_KEYS, reason="GEMINI_API_KEYS (embeddings) / LLAMA_CLOUD_API_KEY not configured"
)


@_skip
async def test_live_ask_single_document_portfolio_and_abstention(fixture_pdf, db_session):
    store = Neo4jGraphStore()
    seed(store)
    contract_id = "ct_live_ask_phase4"
    store.wipe_contract(contract_id)

    await ingest_and_detect(
        store,
        fixture_pdf("contract_a_conflict.pdf"),
        "contract_a_conflict.pdf",
        contract_id=contract_id,
        db=db_session,
    )

    single = await handle_ask(
        store, db_session, "What does contract_a_conflict.pdf say about liability?", session_id=None
    )
    assert single.type == AskResponseType.CONTRACT_ANSWER
    assert single.sources, single.answer_text

    out_of_scope = await handle_ask(store, db_session, "What's the weather today?", session_id=None)
    assert out_of_scope.type == AskResponseType.OUT_OF_SCOPE

    unknown = await handle_ask(
        store, db_session, "Summarize the contract_zzz_never_uploaded document.", session_id=None
    )
    assert unknown.type == AskResponseType.ABSTAINED

    store.wipe_contract(contract_id)
