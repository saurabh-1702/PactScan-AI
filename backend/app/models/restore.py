"""Pydantic schemas for Document Restore (Phase 6)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class CreateRestoreRequest(BaseModel):
    contract_id: str
    target_version_id: str
    reason: str


class DecideRestoreRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = None


class RestoreRequestOut(BaseModel):
    id: str
    contract_id: str
    target_version_id: str
    target_version_number: int
    requested_by_user_id: str
    requested_by_email: str | None = None
    reason: str
    status: str
    reviewer_note: str | None
    abuse_flagged: bool
    decided_at: datetime | None
    decided_by_email: str | None = None
    created_at: datetime
