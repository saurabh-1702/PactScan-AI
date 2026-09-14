"""Pydantic schemas for Horizon-Scanning (Phase 6)."""

from __future__ import annotations

from pydantic import BaseModel


class SimulateUpdateRequest(BaseModel):
    regulation_name: str
    new_clause_text: str
    effective_date: str


class AffectedContract(BaseModel):
    contract_id: str
    filename: str
    new_finding_ids: list[str]


class SimulateUpdateResult(BaseModel):
    regulation_clause_id: str
    contracts_flagged: int
    findings_created: int
    details: list[AffectedContract]
