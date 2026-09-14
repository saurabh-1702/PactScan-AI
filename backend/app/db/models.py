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

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.agents.detect.graph_store import DEMO_TENANT
from app.db.postgres_client import Base


class RedlineSuggestion(Base):
    __tablename__ = "redline_suggestions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"sg_{uuid.uuid4().hex[:16]}")
    # Added Phase 5 — Phases 2-4 had no Postgres-side tenant column at all
    # (only the Neo4j graph and Phase 4's ChatSession/ChatMessage did), which
    # made real tenant-isolated queries (dashboard, approval listing)
    # impossible. Defaults to DEMO_TENANT so any pre-Phase-5 row a fresh
    # create_all() happens to see still has a valid value.
    tenant_id: Mapped[str] = mapped_column(String(40), index=True, default=DEMO_TENANT)
    # Who asked for this draft — end_user and reviewer/admin alike may draft
    # (see app/core/rate_limit.py's design note). Nullable: a suggestion
    # drafted before this column existed, or via a direct pipeline call with
    # no authenticated caller, has no traceable requester, and the decision
    # notification is simply skipped for those.
    requested_by_user_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
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
    # Added Phase 5 alongside RedlineSuggestion.tenant_id, for the same reason:
    # /api/documents/* had no way to confirm a requester's tenant actually owns
    # the document being listed/downloaded.
    tenant_id: Mapped[str] = mapped_column(String(40), index=True, default=DEMO_TENANT)
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


class Tenant(Base):
    """Phase 5: real multi-tenant identity, replacing the hardcoded
    DEMO_TENANT string every prior phase used directly. One row
    (id=DEMO_TENANT) is seeded at startup so existing Neo4j/Postgres data
    keeps resolving to a real tenant."""

    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"usr_{uuid.uuid4().hex[:16]}")
    tenant_id: Mapped[str] = mapped_column(String(40), ForeignKey("tenants.id"), index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(20))  # "end_user" | "reviewer" | "admin"
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class Notification(Base):
    """Two kinds, distinguished by ``kind``:

    - ``new_finding`` — fired once per new Finding (see
      app/agents/notifications/notify.py), right after Detect writes it to
      the graph. Broadcast tenant-wide (``recipient_user_id`` is None) since
      any reviewer/admin/end_user may care that a new issue was found.
      HIGH severity additionally attempts a best-effort email via Resend.
    - ``approval_decided`` — fired once a reviewer/admin decides a pending
      approval (see app/api/approvals.py), addressed to the specific user
      who requested that draft (``recipient_user_id`` set,
      ``RedlineSuggestion.requested_by_user_id``) — skipped entirely if that
      draft has no traceable requester. Carries ``document_version_id`` when
      the decision produced a downloadable document (i.e. any 'approved'
      outcome), so the requester can download it straight from the bell
      without needing access to /approvals.
    """

    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"ntf_{uuid.uuid4().hex[:16]}")
    kind: Mapped[str] = mapped_column(String(30), default="new_finding")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    # None = broadcast to every user in the tenant (all new_finding rows);
    # set = addressed to exactly one user (all approval_decided rows).
    recipient_user_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    finding_id: Mapped[str | None] = mapped_column(String(40), nullable=True, index=True)
    severity: Mapped[str | None] = mapped_column(String(10), nullable=True)
    message: Mapped[str] = mapped_column(Text)
    document_version_id: Mapped[str | None] = mapped_column(String(40), nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )


class ChatSession(Base):
    """One Ask-agent conversation, scoped to the user who started it (Phase 5
    — Phase 4 only had tenant_id, since login/roles didn't exist yet).
    Nullable only so a pre-Phase-5 row surviving a schema reset doesn't
    violate a NOT NULL constraint; every row created from here on always
    sets it."""

    __tablename__ = "chat_sessions"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"cs_{uuid.uuid4().hex[:16]}")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True)
    user_id: Mapped[str | None] = mapped_column(String(40), index=True, nullable=True)
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


class RestoreRequest(Base):
    """Phase 6 — a client's request to revert a document to a prior version,
    gated by the exact same reviewer/admin approval requirement as any other
    edit (require_role(["reviewer", "admin"]) on the decide endpoint), just
    via a parallel table/endpoint rather than reusing Approval/RedlineSuggestion
    — those are hard-wired to an AI-drafted redline (proposed_text, rationale,
    contrarian/judge/negotiation JSON), none of which fit "restore to version
    N", and Approval.redline_suggestion_id is a hard FK that can't point
    anywhere else."""

    __tablename__ = "restore_requests"

    id: Mapped[str] = mapped_column(String(40), primary_key=True, default=lambda: f"rr_{uuid.uuid4().hex[:16]}")
    tenant_id: Mapped[str] = mapped_column(String(40), index=True, default=DEMO_TENANT)
    contract_id: Mapped[str] = mapped_column(String(40), index=True)
    target_version_id: Mapped[str] = mapped_column(String(40), ForeignKey("document_versions.id"))
    requested_by_user_id: Mapped[str] = mapped_column(String(40), index=True)
    reason: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    reviewer_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Set at request-creation time by app/agents/restore/abuse_check.py — 2+
    # already-approved restores for this contract within the flagging window.
    # Never blocks; only surfaces a warning banner in the approval queue.
    abuse_flagged: Mapped[bool] = mapped_column(Boolean, default=False)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
