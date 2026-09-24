"""Pydantic schemas for a requester's own drafts (Phase 6b)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class SubmitDraftRequest(BaseModel):
    # None / empty / identical to the AI text = "submit the AI draft as-is"
    edited_text: str | None = None


class DraftOut(BaseModel):
    """One suggestion, with all three texts that can exist for it:
    the AI draft, the requester's own edit of it (if any), and the
    reviewer's edit at decision time (if any) — so a requester can see what
    changed at each step."""

    suggestion_id: str
    contract_id: str
    filename: str | None
    clause_id: str
    finding_id: str | None
    original_clause_text: str
    ai_draft_text: str
    requester_edited_text: str | None
    rationale: str
    confidence: int

    # "draft" = generated but not yet submitted to a reviewer
    status: Literal["draft", "pending", "approved", "rejected"]
    approval_id: str | None
    reviewer_edited_text: str | None
    reviewer_note: str | None
    document_version_id: str | None

    created_at: datetime
    submitted_at: datetime | None
    decided_at: datetime | None
    decided_by_email: str | None = None
