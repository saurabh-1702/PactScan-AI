"""Pydantic schemas for the Suggest agent (Phase 2).

Suggest never writes to a file — every model here describes a draft only.
File writes (approval-gated) are Phase 3.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class RelatedClause(BaseModel):
    """A semantically-related clause surfaced by vector search."""

    clause_id: str
    contract_id: str
    clause_type: str
    raw_text: str
    similarity: float


class OverrideContext(BaseModel):
    clause_id: str
    raw_text: str
    page_number: int
    scope: str = ""
    direction: str  # "overrides" | "overridden_by"


class RetrievedContext(BaseModel):
    """Everything gathered before drafting — the Retriever's output."""

    clause_id: str
    clause_raw_text: str
    violated_rule_or_regulation_text: str
    violated_rule_or_regulation_label: str
    related_clauses: list[RelatedClause] = Field(default_factory=list)
    override_context: list[OverrideContext] = Field(default_factory=list)
    change_request: str  # the finding's explanation, or the user's free-text request


# --------------------------------------------------------------------------- #
# LLM I/O schemas
# --------------------------------------------------------------------------- #
class ProposedRedline(BaseModel):
    proposed_clause_text: str
    rationale: str
    confidence: int = Field(ge=0, le=100)


class ContrarianArgument(BaseModel):
    argument: str
    strongest_point: str
    confidence: int = Field(ge=0, le=100)


class JudgeVerdict(BaseModel):
    verdict: str  # "confirmed" | "downgraded" | "dismissed"
    final_confidence: int = Field(ge=0, le=100)
    reasoning: str


class NegotiationFallback(BaseModel):
    predicted_pushback: str
    fallback_clause_text: str


# --------------------------------------------------------------------------- #
# API / persistence
# --------------------------------------------------------------------------- #
class SuggestResult(BaseModel):
    suggestion_id: str
    finding_id: str | None
    contract_id: str
    clause_id: str
    proposed_text: str
    rationale: str
    confidence: int
    contrarian: ContrarianArgument | None = None
    judge: JudgeVerdict | None = None
    negotiation: NegotiationFallback | None = None
    created_at: datetime
    # None while this is only a draft (Phase 6b) — set once it's been submitted
    approval_id: str | None = None


class StandaloneSuggestRequest(BaseModel):
    contract_id: str
    clause_id: str
    change_request: str
