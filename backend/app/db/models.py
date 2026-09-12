"""SQLAlchemy ORM models — operational state that belongs in PostgreSQL
(as opposed to the Neo4j knowledge graph).

No migration framework yet (Alembic) — Phase 0 didn't set one up, and for a
single new table `Base.metadata.create_all()` at startup is idempotent and
sufficient. Worth introducing Alembic once schema changes get frequent
(tracked for a later phase, e.g. when Phase 5 adds tenants/users/roles).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.postgres_client import Base


class RedlineSuggestion(Base):
    __tablename__ = "redline_suggestions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"sg_{uuid.uuid4().hex[:16]}")
    finding_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    contract_id: Mapped[str] = mapped_column(String(40), index=True)
    clause_id: Mapped[str] = mapped_column(String(40), index=True)
    proposed_text: Mapped[str] = mapped_column(Text)
    rationale: Mapped[str] = mapped_column(Text)
    confidence: Mapped[int] = mapped_column(Integer)
    contrarian_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    judge_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    negotiation_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Approval(Base):
    """The human-in-the-loop gate. `status` starts 'pending' (auto-created right
    after a Suggest call succeeds) and is only ever changed by
    POST /api/approvals/{id}/decide.

    `edited_text` is an addition beyond the Phase 3 prompt's literal schema —
    needed so a reviewer's "Edit" action (required by the frontend spec) has
    somewhere to persist to; when set, the Executor writes this instead of the
    original `proposed_text`.
    """

    __tablename__ = "approvals"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"apv_{uuid.uuid4().hex[:16]}")
    redline_suggestion_id: Mapped[str] = mapped_column(
        String(40), ForeignKey("redline_suggestions.id"), index=True
    )
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class DocumentVersion(Base):
    """Every write is a new row + a new file — nothing is ever edited in place.
    `approval_id` is NULL for the original (version 1) capture; set to the
    approval that authorized the write for every version after that.
    """

    __tablename__ = "document_versions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"dv_{uuid.uuid4().hex[:16]}")
    contract_id: Mapped[str] = mapped_column(String(40), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    file_path: Mapped[str] = mapped_column(String(500))
    approval_id: Mapped[str | None] = mapped_column(
        String(40), ForeignKey("approvals.id"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class AuditLog(Base):
    """Append-only. Every state-changing action from Phase 3 onward writes a row."""

    __tablename__ = "audit_log"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"al_{uuid.uuid4().hex[:16]}")
    event_type: Mapped[str] = mapped_column(String(50), index=True)
    entity_id: Mapped[str] = mapped_column(String(40), index=True)
    details: Mapped[str] = mapped_column(Text)  # JSON-serialized, like Phase 2's *_json columns
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class PlaybookFeedback(Base):
    """Lightweight stand-in for the full 'update the compliance playbook'
    learning loop — for Phase 3, just proves the accepted-redline data is
    actually being captured."""

    __tablename__ = "playbook_feedback"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"pf_{uuid.uuid4().hex[:16]}")
    clause_type: Mapped[str] = mapped_column(String(60))
    accepted_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ChatSession(Base):
    """One Ask-agent conversation. Tenant-wide, not yet per-user — Phase 5
    adds login/roles, at which point this gains a user_id column."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"cs_{uuid.uuid4().hex[:16]}")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    title: Mapped[str] = mapped_column(String(200), default="New conversation")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ChatMessage(Base):
    """One turn in a ChatSession. `sources_json` / `suggestion_id` /
    `approval_id` are only ever set on assistant messages."""

    __tablename__ = "chat_messages"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"cm_{uuid.uuid4().hex[:16]}")
    session_id: Mapped[str] = mapped_column(String(40), ForeignKey("chat_sessions.id"), index=True)
    role: Mapped[str] = mapped_column(String(10))  # "user" | "assistant"
    content: Mapped[str] = mapped_column(Text)
    response_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    sources_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestion_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    approval_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
