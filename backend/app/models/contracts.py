"""Pydantic schemas for the contract list and current-user endpoints."""

from __future__ import annotations

from datetime import datetime

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


class RescanBlockers(BaseModel):
    pending_approvals: int = 0
    pending_restores: int = 0
    unsubmitted_drafts: int = 0


class ScanInfo(BaseModel):
    latest_version: int
    scanned_version: int
    # True when the current wording differs from the version the findings describe
    stale: bool
    running: bool
    # a re-scan started but did not finish after replacing the analysis
    incomplete: bool
    last_rescan_at: datetime | None = None
    blockers: RescanBlockers
    can_rescan: bool


class RescanRequest(BaseModel):
    job_id: str | None = None


class RescanResult(BaseModel):
    contract_id: str
    scanned_version: int
    findings_before: int
    findings_after: int
