"""Ask agent tests (mocked LLM + embeddings + LlamaParse, in-memory graph +
SQLite). Covers the 4 required routing cases (single-document, portfolio,
out-of-scope, unknown-document abstention) plus general-legal-tech,
compliance-status, threshold-based abstention, and chat persistence.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest

from app.agents.ask.pipeline import handle_ask
from app.agents.detect.pipeline import ingest_and_detect
from app.config import settings
from app.db.models import Approval, ChatMessage, ChatSession, RedlineSuggestion
from app.models.ask import AskResponseType

pytestmark = pytest.mark.asyncio


async def _ingest(seeded_store, fixture_pdf, db_session, name: str, contract_id: str):
    return await ingest_and_detect(
        seeded_store, fixture_pdf(name), name, contract_id=contract_id, db=db_session
    )


async def test_single_document_question_cites_that_document(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session
):
    await _ingest(seeded_store, fixture_pdf, db_session, "contract_a_conflict.pdf", "ct_a")

    response = await handle_ask(
        seeded_store, db_session, "What does contract_a_conflict say about liability?", session_id=None
    )

    assert response.type == AskResponseType.CONTRACT_ANSWER
    assert response.sources, "expected at least one citation"
    # regulation excerpts are always folded in too (see ask_retriever.py), so
    # assert the named document is cited, not that it's the *only* citation
    assert any(s.document_name == "contract_a_conflict.pdf" for s in response.sources)


async def test_portfolio_question_cites_multiple_documents(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session
):
    await _ingest(seeded_store, fixture_pdf, db_session, "contract_a_conflict.pdf", "ct_a")
    await _ingest(seeded_store, fixture_pdf, db_session, "contract_b_regulation_gap.pdf", "ct_b")

    response = await handle_ask(
        seeded_store, db_session, "Which of our contracts mention a liability cap?", session_id=None
    )

    assert response.type == AskResponseType.CONTRACT_ANSWER
    document_names = {s.document_name for s in response.sources}
    assert len(document_names) >= 2, document_names


async def test_out_of_scope_question_is_declined(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session
):
    response = await handle_ask(seeded_store, db_session, "What's the weather today?", session_id=None)
    assert response.type == AskResponseType.OUT_OF_SCOPE
    assert response.sources == []


async def test_unknown_document_abstains_rather_than_fabricating(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session
):
    await _ingest(seeded_store, fixture_pdf, db_session, "contract_a_conflict.pdf", "ct_a")

    response = await handle_ask(
        seeded_store, db_session, "Summarize the contract_z_never_uploaded document.", session_id=None
    )

    assert response.type == AskResponseType.ABSTAINED
    assert "don't have" in response.answer_text.lower()
    assert response.sources == []


async def test_general_legal_tech_question_is_not_portfolio_grounded(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session
):
    response = await handle_ask(seeded_store, db_session, "What is the DPDP Act?", session_id=None)
    assert response.type == AskResponseType.GENERAL_INFO
    assert response.sources == []


async def test_compliance_status_question_reports_findings(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session
):
    await _ingest(seeded_store, fixture_pdf, db_session, "contract_a_conflict.pdf", "ct_a")

    response = await handle_ask(
        seeded_store, db_session, "What issues were detected in our contracts?", session_id=None
    )

    assert response.type == AskResponseType.STATUS_ANSWER
    assert any(s.document_name == "contract_a_conflict.pdf" for s in response.sources)


async def test_similarity_threshold_forces_abstention(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session, monkeypatch
):
    """The fake embeddings don't naturally produce low similarity, so this
    proves the threshold branch itself works by making it unreachable-high."""
    await _ingest(seeded_store, fixture_pdf, db_session, "contract_a_conflict.pdf", "ct_a")
    monkeypatch.setattr(settings, "ask_similarity_threshold", 999.0)

    response = await handle_ask(
        seeded_store, db_session, "What does contract_a_conflict say about liability?", session_id=None
    )

    assert response.type == AskResponseType.ABSTAINED


async def test_edit_instruction_creates_pending_approval_and_touches_no_file(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session
):
    await _ingest(seeded_store, fixture_pdf, db_session, "contract_a_conflict.pdf", "ct_a")
    from app.db.models import DocumentVersion

    v1 = db_session.query(DocumentVersion).filter_by(contract_id="ct_a").one()
    before_hash = hashlib.sha256(Path(v1.file_path).read_bytes()).hexdigest()

    response = await handle_ask(
        seeded_store,
        db_session,
        "Edit contract_a_conflict to change the liability cap to Rupees 2,00,00,000.",
        session_id=None,
    )

    assert response.type == AskResponseType.EDIT_DRAFT
    assert response.suggestion_id is not None
    assert response.approval_id is not None

    suggestion = db_session.get(RedlineSuggestion, response.suggestion_id)
    assert suggestion is not None
    approval = db_session.get(Approval, response.approval_id)
    assert approval is not None
    assert approval.status == "pending"

    assert hashlib.sha256(Path(v1.file_path).read_bytes()).hexdigest() == before_hash
    assert db_session.query(DocumentVersion).filter_by(contract_id="ct_a").count() == 1


async def test_chat_history_is_persisted_across_turns(
    seeded_store, fake_llm, fake_parse, fake_embed, fixture_pdf, db_session
):
    await _ingest(seeded_store, fixture_pdf, db_session, "contract_a_conflict.pdf", "ct_a")

    first = await handle_ask(seeded_store, db_session, "What's the weather today?", session_id=None)
    session_id = first.session_id

    second = await handle_ask(
        seeded_store, db_session, "What is the DPDP Act?", session_id=session_id
    )
    assert second.session_id == session_id  # same conversation, not a new one

    session = db_session.get(ChatSession, session_id)
    assert session is not None
    messages = (
        db_session.query(ChatMessage)
        .filter_by(session_id=session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    # 2 user turns + 2 assistant turns
    assert len(messages) == 4
    assert [m.role for m in messages] == ["user", "assistant", "user", "assistant"]
