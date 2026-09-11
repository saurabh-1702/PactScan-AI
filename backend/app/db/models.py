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

from sqlalchemy import DateTime, Integer, String, Text
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
