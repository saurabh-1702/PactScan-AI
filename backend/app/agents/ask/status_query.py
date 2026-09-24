"""Ask agent — COMPLIANCE_STATUS_QUESTION.

A different retrieval mode from CONTRACT_QUESTION: this queries the system's
own operational records (Neo4j Findings; Postgres redline_suggestions /
approvals) rather than searching clause content by meaning. Optionally scoped
to one document and/or a time window.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.agents.ask.ask_retriever import contract_by_id, find_contract_by_name
from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.db.models import Approval, RedlineSuggestion
from app.llm import client as llm
from app.models.ask import AskAnswer, DocumentScope

_RELATIVE_PHRASES: dict[str, timedelta] = {
    "today": timedelta(days=1),
    "yesterday": timedelta(days=2),
    "this week": timedelta(days=7),
    "last week": timedelta(days=7),
    "this month": timedelta(days=30),
    "last month": timedelta(days=30),
    "this year": timedelta(days=365),
    "last year": timedelta(days=365),
}

_STATUS_SYSTEM_PROMPT = (
    "You summarize a compliance tool's own results for the user — Detect's findings, "
    "Suggest's drafted redlines, and their approval status. Use ONLY the structured "
    "facts provided below; never invent a finding, document, or outcome that isn't "
    "listed. Cite the document name for every item you mention. If the facts list is "
    "empty, say so plainly rather than inventing something. Populate the structured "
    "`sources` field with the (document_name, page_number) pairs you referenced — use "
    "page_number 0 for items with no natural page (e.g. a redline suggestion)."
)


def parse_time_reference(text: str | None) -> datetime | None:
    """Best-effort parse of a plain-language relative time reference into a UTC
    cutoff datetime. Returns None (meaning 'no cutoff, show everything') if it
    can't be confidently parsed — never raises."""
    if not text or not text.strip():
        return None
    t = text.strip().lower()
    now = datetime.now(timezone.utc)

    for phrase, delta in _RELATIVE_PHRASES.items():
        if phrase in t:
            return now - delta

    m = re.search(r"(\d+)\s*(day|week|month|year)s?", t)
    if m:
        n = int(m.group(1))
        multiplier = {"day": 1, "week": 7, "month": 30, "year": 365}[m.group(2)]
        return now - timedelta(days=n * multiplier)

    try:
        from dateutil import parser as dateutil_parser

        dt = dateutil_parser.parse(text, fuzzy=True, default=now)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt if dt <= now else None
    except (ValueError, OverflowError, TypeError):
        return None


def build_status_summary(
    store: GraphStore,
    db: Session,
    document_scope: DocumentScope,
    mentioned_document_name: str | None,
    time_reference: str | None,
    tenant_id: str = DEMO_TENANT,
    owner_user_id: str | None = None,
    contract_id_override: str | None = None,
) -> dict:
    document_name = None
    contract_id = None
    if contract_id_override is not None:
        match = contract_by_id(store, contract_id_override, tenant_id, owner_user_id)
        if match is None:
            return {"items": [], "not_found": True, "document_name": "the attached document"}
        contract_id = match["contract_id"]
        document_name = match["filename"]
    elif document_scope == DocumentScope.SINGLE:
        match = find_contract_by_name(
            store, mentioned_document_name or "", tenant_id=tenant_id, owner_user_id=owner_user_id
        )
        if match is None:
            return {"items": [], "not_found": True, "document_name": mentioned_document_name}
        contract_id = match["contract_id"]
        document_name = match["filename"]

    cutoff = parse_time_reference(time_reference)
    filenames = {
        c["contract_id"]: c["filename"]
        for c in store.list_contracts(tenant_id=tenant_id, owner_user_id=owner_user_id)
    }
    contract_ids = [contract_id] if contract_id else list(filenames.keys())

    items: list[dict] = []
    for cid in contract_ids:
        for f in store.get_findings(cid, tenant_id=tenant_id):
            items.append(
                {
                    "kind": "finding",
                    "document_name": filenames.get(cid, cid),
                    "severity": f.severity.value,
                    "clause_type": f.clause_type.value,
                    "page_number": f.page_number,
                    "rule_or_regulation_violated": f.rule_or_regulation_violated,
                    "explanation": f.explanation,
                }
            )

    # tenant + (for an end_user) ownership scoped — this query previously had
    # no tenant filter at all
    q = db.query(RedlineSuggestion).filter(
        RedlineSuggestion.tenant_id == tenant_id,
        RedlineSuggestion.contract_id.in_(contract_ids),
    )
    if cutoff:
        q = q.filter(RedlineSuggestion.created_at >= cutoff)
    for s in q.order_by(RedlineSuggestion.created_at.desc()).limit(50).all():
        approval = (
            db.query(Approval)
            .filter(Approval.redline_suggestion_id == s.id)
            .order_by(Approval.created_at.desc())
            .first()
        )
        items.append(
            {
                "kind": "suggestion",
                "document_name": filenames.get(s.contract_id, s.contract_id),
                "proposed_text": s.proposed_text,
                "rationale": s.rationale,
                "confidence": s.confidence,
                "approval_status": approval.status if approval else "draft (not yet submitted for review)",
                "created_at": s.created_at.isoformat(),
            }
        )

    return {
        "items": items,
        "not_found": False,
        "document_name": document_name,
        "cutoff": cutoff.isoformat() if cutoff else None,
    }


def _describe(item: dict) -> str:
    if item["kind"] == "finding":
        return (
            f"Finding: {item['severity']} severity — {item['rule_or_regulation_violated']} "
            f"(page {item['page_number']}): {item['explanation']}"
        )
    return (
        f"Suggested redline (confidence {item['confidence']}, approval status "
        f"'{item['approval_status']}'): {item['rationale']}"
    )


async def generate_status_answer(
    question: str, items: list[dict], document_name: str | None
) -> AskAnswer:
    if not items:
        scope_note = f" for {document_name}" if document_name else " in your portfolio"
        return AskAnswer(
            answer_text=(
                f"I don't have any recorded findings, suggestions, or approvals{scope_note} "
                "matching that."
            ),
            sources=[],
        )

    facts = "\n".join(f"- [{it['document_name']}] {_describe(it)}" for it in items)
    prompt = f"QUESTION:\n{question}\n\nRECORDED FACTS:\n{facts}\n\nSummarize, citing document names."
    answer = await llm.generate_structured(prompt=prompt, schema=AskAnswer, system_prompt=_STATUS_SYSTEM_PROMPT)

    valid_names = {it["document_name"] for it in items}
    answer.sources = [s for s in answer.sources if s.document_name in valid_names]
    return answer
