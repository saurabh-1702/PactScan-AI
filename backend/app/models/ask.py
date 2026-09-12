"""Pydantic schemas for the Ask agent (Phase 4)."""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, Field


class AskScope(str, enum.Enum):
    CONTRACT_QUESTION = "CONTRACT_QUESTION"  # clause content — grounded via vector search
    COMPLIANCE_STATUS_QUESTION = "COMPLIANCE_STATUS_QUESTION"  # what Detect/Suggest/Fix & Learn did
    EDIT_INSTRUCTION = "EDIT_INSTRUCTION"  # hands off to Suggest, never bypasses approval
    GENERAL_LEGAL_TECH_QUESTION = "GENERAL_LEGAL_TECH_QUESTION"  # general knowledge, not portfolio-grounded
    OUT_OF_SCOPE = "OUT_OF_SCOPE"


class DocumentScope(str, enum.Enum):
    PORTFOLIO = "portfolio"
    SINGLE = "single"


class ScopeClassification(BaseModel):
    """One LLM call does triple duty: classify the message, and (where
    relevant) extract the document it names and/or the change it requests —
    avoids a second round-trip for EDIT_INSTRUCTION / SINGLE-document cases."""

    scope: AskScope
    document_scope: DocumentScope = DocumentScope.PORTFOLIO
    mentioned_document_name: str | None = None
    requested_change: str | None = None  # only meaningful for EDIT_INSTRUCTION
    time_reference: str | None = None  # only meaningful for COMPLIANCE_STATUS_QUESTION, e.g. "last week"
    reasoning: str = ""


class AskSource(BaseModel):
    document_name: str
    page_number: int


class AskAnswer(BaseModel):
    """LLM output for a CONTRACT_QUESTION. ``sources`` is validated against
    what was actually retrieved before being trusted (app/agents/ask/answer_generator.py)."""

    answer_text: str
    sources: list[AskSource] = Field(default_factory=list)


class GeneralLegalAnswer(BaseModel):
    """LLM output for a GENERAL_LEGAL_TECH_QUESTION — no sources, since it's
    explicitly not grounded in the tenant's own documents."""

    answer_text: str


class AskRequest(BaseModel):
    message: str
    session_id: str | None = None  # omit to start a new session


class AskResponseType(str, enum.Enum):
    CONTRACT_ANSWER = "contract_answer"
    STATUS_ANSWER = "status_answer"
    EDIT_DRAFT = "edit_draft"
    GENERAL_INFO = "general_info"
    OUT_OF_SCOPE = "out_of_scope"
    ABSTAINED = "abstained"


class AskResponse(BaseModel):
    session_id: str
    type: AskResponseType
    answer_text: str
    sources: list[AskSource] = Field(default_factory=list)
    suggestion_id: str | None = None
    approval_id: str | None = None


class ChatSessionOut(BaseModel):
    id: str
    title: str
    created_at: datetime
    updated_at: datetime
    message_count: int = 0


class ChatMessageOut(BaseModel):
    id: str
    role: str
    content: str
    response_type: str | None = None
    sources: list[AskSource] = Field(default_factory=list)
    suggestion_id: str | None = None
    approval_id: str | None = None
    created_at: datetime
