"""Pydantic schemas for the approval queue / Fix & Learn API (Phase 3)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field


class CreateApprovalRequest(BaseModel):
    redline_suggestion_id: str


class DecideRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    note: str | None = None
    # If set on an "approved" decision, the Executor writes this text instead
    # of the original proposed_text — the reviewer's "Edit" action.
    edited_text: str | None = None


class ApprovalOut(BaseModel):
    id: str
    redline_suggestion_id: str
    status: str
    reviewer_note: str | None
    edited_text: str | None
    decided_at: datetime | None
    created_at: datetime

    # denormalized fields from the associated redline_suggestions row, so the
    # frontend doesn't need a second round-trip per item
    finding_id: str | None
    contract_id: str
    clause_id: str
    original_clause_text: str
    proposed_text: str
    rationale: str
    confidence: int


class DocumentVersionOut(BaseModel):
    id: str
    contract_id: str
    version_number: int
    approval_id: str | None
    created_at: datetime
