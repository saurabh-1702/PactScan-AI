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


class AffectedContractRef(BaseModel):
    contract_id: str
    filename: str


class RegulationUpdateOut(BaseModel):
    """One entry in the regulatory-update log."""

    id: str
    regulation_name: str
    jurisdiction: str | None = None
    section: str
    text: str
    effective_date: str | None = None
    # "update" = an amendment added through Horizon-Scanning (simulated);
    # "baseline" = a clause seeded at startup.
    kind: str
    # contracts (visible to the caller) that this update produced findings on
    affected_contracts: list[AffectedContractRef] = []
