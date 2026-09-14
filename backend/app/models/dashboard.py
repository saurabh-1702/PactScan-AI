"""Pydantic schemas for the dashboard (Phase 5) — a read-only visualization
layer over data Phases 1-3 already computed. Nothing here is newly computed."""

from __future__ import annotations

from pydantic import BaseModel


class DashboardOverview(BaseModel):
    total_contracts: int
    findings_by_severity: dict[str, int]
    approvals_by_status: dict[str, int]


class PipelineFinding(BaseModel):
    finding_id: str
    contract_id: str
    severity: str
    rule_or_regulation_violated: str


class FindingsPipeline(BaseModel):
    new_finding: list[PipelineFinding]
    redline_suggested: list[PipelineFinding]
    pending_approval: list[PipelineFinding]
    fixed_applied: list[PipelineFinding]
    rejected: list[PipelineFinding]
