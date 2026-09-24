"""Ask agent API.

POST /api/ask                              -> ask a question / issue an edit instruction
GET  /api/ask/sessions                     -> list the caller's own past conversations
GET  /api/ask/sessions/{session_id}/messages -> replay one of the caller's own conversations
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agents.detect.graph_store import GraphStore, get_graph_store
from app.agents.ask.pipeline import ChatSessionAccessError, handle_ask
from app.api.access import owner_scope
from app.api.deps import CurrentUser, get_current_user
from app.db.models import ChatMessage, ChatSession
from app.db.postgres_client import get_db
from app.models.ask import AskRequest, AskResponse, AskSource, ChatMessageOut, ChatSessionOut

logger = logging.getLogger("pactscan.api.ask")

router = APIRouter(prefix="/api/ask", tags=["ask"])


def get_store() -> GraphStore:
    return get_graph_store()


@router.post("", response_model=AskResponse)
async def ask(
    body: AskRequest,
    store: GraphStore = Depends(get_store),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> AskResponse:
    try:
        return await handle_ask(
            store,
            db,
            body.message,
            body.session_id,
            tenant_id=current_user.tenant_id,
            user_id=current_user.user_id,
            owner_user_id=owner_scope(current_user),
        )
    except ChatSessionAccessError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Ask pipeline failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/sessions", response_model=list[ChatSessionOut])
def list_sessions(
    db: Session = Depends(get_db), current_user: CurrentUser = Depends(get_current_user)
) -> list[ChatSessionOut]:
    rows = (
        db.query(ChatSession, func.count(ChatMessage.id))
        .outerjoin(ChatMessage, ChatMessage.session_id == ChatSession.id)
        .filter(
            ChatSession.tenant_id == current_user.tenant_id,
            ChatSession.user_id == current_user.user_id,
        )
        .group_by(ChatSession.id)
        .order_by(ChatSession.updated_at.desc())
        .all()
    )
    return [
        ChatSessionOut(
            id=s.id, title=s.title, created_at=s.created_at, updated_at=s.updated_at, message_count=count
        )
        for s, count in rows
    ]


@router.get("/sessions/{session_id}/messages", response_model=list[ChatMessageOut])
def get_session_messages(
    session_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ChatMessageOut]:
    session = db.get(ChatSession, session_id)
    if (
        session is None
        or session.tenant_id != current_user.tenant_id
        or session.user_id != current_user.user_id
    ):
        raise HTTPException(404, f"chat session {session_id!r} not found")

    rows = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at)
        .all()
    )
    out = []
    for m in rows:
        sources = [AskSource(**s) for s in json.loads(m.sources_json)] if m.sources_json else []
        out.append(
            ChatMessageOut(
                id=m.id,
                role=m.role,
                content=m.content,
                response_type=m.response_type,
                sources=sources,
                suggestion_id=m.suggestion_id,
                approval_id=m.approval_id,
                created_at=m.created_at,
            )
        )
    return out
