"""Pydantic schemas for the contract list and current-user endpoints."""

from __future__ import annotations

from pydantic import BaseModel


class ContractSummary(BaseModel):
    contract_id: str
    filename: str
    uploaded_by_user_id: str | None = None
    uploaded_by_email: str | None = None
    uploaded_at: str | None = None
    high: int = 0
    medium: int = 0
    low: int = 0
    total_findings: int = 0
    version_count: int = 0


class MeOut(BaseModel):
    user_id: str
    email: str
    role: str
    tenant_id: str
    tenant_name: str
