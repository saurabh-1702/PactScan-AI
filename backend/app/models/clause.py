"""Pydantic schemas for the Detect agent.

The clause taxonomy is a deliberately narrowed set, informed by CUAD's category
naming conventions (a taxonomy reference only — CUAD data is never loaded).
Categories not relevant to vendor-DPA compliance are intentionally dropped
(NON_COMPETE, IP_OWNERSHIP, INSURANCE, PAYMENT_TERMS, DISPUTE_RESOLUTION).
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class ClauseType(str, enum.Enum):
    LIMITATION_OF_LIABILITY = "LIMITATION_OF_LIABILITY"
    DATA_PROCESSING = "DATA_PROCESSING"
    DATA_LOCALIZATION_CROSS_BORDER_TRANSFER = "DATA_LOCALIZATION_CROSS_BORDER_TRANSFER"
    TERMINATION = "TERMINATION"
    TERMINATION_FOR_CONVENIENCE = "TERMINATION_FOR_CONVENIENCE"
    CONFIDENTIALITY = "CONFIDENTIALITY"
    GOVERNING_LAW = "GOVERNING_LAW"
    INDEMNIFICATION = "INDEMNIFICATION"
    AUDIT_RIGHTS = "AUDIT_RIGHTS"
    BREACH_NOTIFICATION = "BREACH_NOTIFICATION"
    SUBPROCESSOR_OBLIGATIONS = "SUBPROCESSOR_OBLIGATIONS"
    OTHER = "OTHER"


class ConfidenceLevel(str, enum.Enum):
    high = "high"
    medium = "medium"
    low = "low"


class Severity(str, enum.Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class ExtractedClause(BaseModel):
    clause_id: str
    contract_id: str
    clause_type: ClauseType
    page_number: int = Field(ge=1)
    section_header: str
    raw_text: str
    confidence: ConfidenceLevel


class Finding(BaseModel):
    finding_id: str
    clause_id: str
    clause_type: ClauseType
    page_number: int = Field(ge=1)
    section_header: str
    severity: Severity
    rule_or_regulation_violated: str
    explanation: str
    confidence: ConfidenceLevel
    override_chain: list[str] = Field(default_factory=list)


class DetectReport(BaseModel):
    contract_id: str
    filename: str
    findings: list[Finding] = Field(default_factory=list)
    total_findings: int = 0
    timestamp: datetime | None = None


# --------------------------------------------------------------------------- #
# Internal LLM I/O schemas (structured-output contracts, not API responses)
# --------------------------------------------------------------------------- #
class _LLMClause(BaseModel):
    clause_type: ClauseType
    page_number: int = Field(ge=1)
    section_header: str
    raw_text: str
    confidence: ConfidenceLevel


class ClauseExtractionResult(BaseModel):
    """What ``generate_structured`` returns for the clause-extraction call."""

    clauses: list[_LLMClause] = Field(default_factory=list)


class OverrideCheckResult(BaseModel):
    """Does clause A override / amend / supersede clause B?"""

    overrides: bool
    scope: str = Field(
        default="",
        description="What the override applies to, e.g. 'data-breach events'. Empty if overrides is false.",
    )
    reasoning: str = ""


class NLILabel(str, enum.Enum):
    ENTAILS = "ENTAILS"
    CONTRADICTS = "CONTRADICTS"
    NEUTRAL = "NEUTRAL"


class NLIResult(BaseModel):
    """Classification of a clause against a single rule / regulation."""

    label: NLILabel
    explanation: str
    confidence: ConfidenceLevel
