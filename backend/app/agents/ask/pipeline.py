"""Ask agent — end-to-end orchestration + chat persistence.

    classify -> route (content / status / edit / general / out-of-scope)
             -> persist both turns to chat_sessions / chat_messages

Read-only for questions; the only write path (EDIT_INSTRUCTION) delegates
entirely to Phase 2's Suggest pipeline, which lands in Phase 3's approval
queue — Ask itself never touches a file or the Executor.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.agents.ask.answer_generator import generate_answer
from app.agents.ask.ask_retriever import retrieve_for_content_question
from app.agents.ask.edit_handoff import handle_edit_instruction
from app.agents.ask.general_legal import answer_general_question
from app.agents.ask.scope_classifier import classify_scope
from app.agents.ask.status_query import build_status_summary, generate_status_answer
from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.core.rate_limit import DraftRateLimitExceeded, check_draft_rate_limit
from app.db.models import ChatMessage, ChatSession
from app.models.ask import AskResponse, AskResponseType, AskScope

logger = logging.getLogger("pactscan.ask.pipeline")


class ChatSessionAccessError(Exception):
    """Raised when a caller's session_id exists but belongs to someone else —
    surfaced as a 404 at the API layer (same "don't reveal existence" pattern
    used for cross-tenant document access), not a silent fallback to a new
    session."""


_OUT_OF_SCOPE_MESSAGE = (
    "I can only help with questions about your contract portfolio, its compliance "
    "status, or general legal-tech / data-privacy-regulation topics. That's outside "
    "what I can help with."
)


async def handle_ask(
    store: GraphStore,
    db: Session,
    message: str,
    session_id: str | None,
    tenant_id: str = DEMO_TENANT,
    user_id: str | None = None,
) -> AskResponse:
    session = _get_or_create_session(db, session_id, tenant_id, user_id, message)
    _record_message(db, session.id, role="user", content=message)

    classification = await classify_scope(message)
    response = await _route(store, db, message, classification, tenant_id, user_id)
    response.session_id = session.id

    _record_message(
        db,
        session.id,
        role="assistant",
        content=response.answer_text,
        response_type=response.type.value,
        sources=[s.model_dump() for s in response.sources] or None,
        suggestion_id=response.suggestion_id,
        approval_id=response.approval_id,
    )
    session.updated_at = datetime.now(timezone.utc)
    db.commit()

    return response


async def _route(
    store: GraphStore,
    db: Session,
    message: str,
    classification,
    tenant_id: str,
    user_id: str | None = None,
) -> AskResponse:
    if classification.scope == AskScope.OUT_OF_SCOPE:
        return AskResponse(session_id="", type=AskResponseType.OUT_OF_SCOPE, answer_text=_OUT_OF_SCOPE_MESSAGE)

    if classification.scope == AskScope.GENERAL_LEGAL_TECH_QUESTION:
        answer = await answer_general_question(message)
        return AskResponse(session_id="", type=AskResponseType.GENERAL_INFO, answer_text=answer.answer_text)

    if classification.scope == AskScope.EDIT_INSTRUCTION:
        # Drafting is safe for any role (nothing writes without a separate
        # reviewer/admin approval) but is rate-limited per user, same as the
        # Suggest API — see app/core/rate_limit.py. Skipped when user_id is
        # unavailable (e.g. a direct pipeline call with no authenticated caller).
        if user_id is not None:
            try:
                check_draft_rate_limit(user_id)
            except DraftRateLimitExceeded as exc:
                return AskResponse(
                    session_id="",
                    type=AskResponseType.RATE_LIMITED,
                    answer_text=(
                        f"You're drafting edits too quickly — try again in "
                        f"{exc.retry_after_seconds}s."
                    ),
                )
        return await handle_edit_instruction(store, db, classification, tenant_id=tenant_id)

    if classification.scope == AskScope.COMPLIANCE_STATUS_QUESTION:
        summary = build_status_summary(
            store,
            db,
            classification.document_scope,
            classification.mentioned_document_name,
            classification.time_reference,
            tenant_id=tenant_id,
        )
        if summary.get("not_found"):
            label = summary.get("document_name") or "that document"
            return AskResponse(
                session_id="",
                type=AskResponseType.ABSTAINED,
                answer_text=f"I don't have a document matching {label!r} in your portfolio.",
            )
        answer = await generate_status_answer(message, summary["items"], summary.get("document_name"))
        return AskResponse(
            session_id="", type=AskResponseType.STATUS_ANSWER, answer_text=answer.answer_text, sources=answer.sources
        )

    # AskScope.CONTRACT_QUESTION
    retrieval = await retrieve_for_content_question(
        store, message, classification.document_scope, classification.mentioned_document_name, tenant_id=tenant_id
    )
    if retrieval.abstain:
        return AskResponse(session_id="", type=AskResponseType.ABSTAINED, answer_text=retrieval.abstain_reason)
    answer = await generate_answer(message, retrieval.items)
    return AskResponse(
        session_id="", type=AskResponseType.CONTRACT_ANSWER, answer_text=answer.answer_text, sources=answer.sources
    )


def _get_or_create_session(
    db: Session, session_id: str | None, tenant_id: str, user_id: str | None, first_message: str
) -> ChatSession:
    if session_id:
        existing = db.get(ChatSession, session_id)
        if existing is not None:
            if existing.tenant_id != tenant_id or existing.user_id != user_id:
                raise ChatSessionAccessError(
                    f"Chat session {session_id!r} does not belong to this user."
                )
            return existing
    title = (first_message[:60] + "…") if len(first_message) > 60 else first_message
    session = ChatSession(tenant_id=tenant_id, user_id=user_id, title=title or "New conversation")
    db.add(session)
    db.commit()
    db.refresh(session)
    return session


def _record_message(
    db: Session,
    session_id: str,
    role: str,
    content: str,
    response_type: str | None = None,
    sources: list[dict] | None = None,
    suggestion_id: str | None = None,
    approval_id: str | None = None,
) -> None:
    db.add(
        ChatMessage(
            session_id=session_id,
            role=role,
            content=content,
            response_type=response_type,
            sources_json=json.dumps(sources) if sources else None,
            suggestion_id=suggestion_id,
            approval_id=approval_id,
        )
    )
    db.commit()
