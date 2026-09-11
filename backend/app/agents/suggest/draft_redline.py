"""Suggest agent — drafting.

Turns a RetrievedContext into a proposed redline + rationale. Returns data
only — never touches a file (Phase 3 owns the approval-gated write).
"""

from __future__ import annotations

from app.llm import client as llm
from app.models.redline import ProposedRedline, RetrievedContext

_DRAFT_SYSTEM_PROMPT = (
    "You are a contract-redlining assistant for a vendor Data Processing Agreement "
    "compliance tool. Given an original clause, the compliance requirement it fails "
    "or the change the client wants, and related context from the same contract "
    "portfolio, draft a replacement clause that resolves the issue while staying as "
    "close as possible to the original clause's structure, defined terms, and "
    "drafting style. Do not invent facts (parties, amounts, dates) not present in "
    "the provided context. If the requirement implies a specific number or "
    "threshold, use it; otherwise keep the original's numbers unless the change "
    "request says to change them. Provide a short, concrete rationale a legal "
    "reviewer can act on, and a confidence score reflecting how directly the "
    "context supports this specific redline."
)


def _context_block(ctx: RetrievedContext) -> str:
    parts = [
        f"ORIGINAL CLAUSE:\n{ctx.clause_raw_text}",
        f"\nREQUIREMENT / CHANGE REQUESTED:\n{ctx.violated_rule_or_regulation_label}\n"
        f"{ctx.violated_rule_or_regulation_text}",
        f"\nWHY THIS WAS FLAGGED (or the user's request):\n{ctx.change_request}",
    ]
    if ctx.override_context:
        lines = "\n".join(
            f"- {o.direction} clause on page {o.page_number}"
            + (f" (scope: {o.scope})" if o.scope else "")
            + f": {o.raw_text}"
            for o in ctx.override_context
        )
        parts.append(f"\nRELATED OVERRIDE CONTEXT:\n{lines}")
    if ctx.related_clauses:
        lines = "\n".join(
            f"- ({r.clause_type}, similarity {r.similarity:.2f}) {r.raw_text}"
            for r in ctx.related_clauses
        )
        parts.append(f"\nSIMILAR CLAUSES ELSEWHERE IN THE PORTFOLIO (for drafting-style reference only):\n{lines}")
    return "\n".join(parts)


async def draft_redline(ctx: RetrievedContext) -> ProposedRedline:
    prompt = _context_block(ctx) + "\n\nDraft the replacement clause."
    return await llm.generate_structured(
        prompt=prompt, schema=ProposedRedline, system_prompt=_DRAFT_SYSTEM_PROMPT
    )
