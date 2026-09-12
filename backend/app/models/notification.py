"""Pydantic schemas for notifications (Phase 5)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class NotificationOut(BaseModel):
    id: str
    finding_id: str
    severity: str
    message: str
    is_read: bool
    created_at: datetime
