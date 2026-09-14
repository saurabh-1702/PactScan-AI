"""Pydantic schemas for notifications (Phase 5)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: str
    kind: str
    finding_id: str | None
    severity: str | None
    message: str
    document_version_id: str | None
    is_read: bool
    created_at: datetime
