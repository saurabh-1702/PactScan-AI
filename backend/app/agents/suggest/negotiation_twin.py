"""Suggest agent — Negotiation Twin.

Predicts the counterparty's most likely pushback on the proposed redline and
drafts one pre-approved fallback clause, so a reviewer walks into negotiation
with a ready fallback rather than improvising one live.
"""

from __future__ import annotations

from app.llm import client as llm
from app.models.redline import NegotiationFallback, ProposedRedline, RetrievedContext

_SYSTEM_PROMPT = (
    "You role-play the counterparty's legal team reviewing a proposed redline. "
    "Predict their single most likely objection or pushback, then draft one "
    "concrete fallback clause the client could offer instead — a middle ground "
    "that still resolves the original compliance issue but is more likely to be "
    "accepted than the first proposal. Do not fabricate facts not present in the "
    "material."
)


async def run_negotiation_twin(
    ctx: RetrievedContext, redline: ProposedRedline
) -> NegotiationFallback:
    prompt = (
        f"ORIGINAL CLAUSE:\n{ctx.clause_raw_text}\n\n"
        f"PROPOSED REDLINE:\n{redline.proposed_clause_text}\n\n"
        f"RATIONALE FOR THE REDLINE:\n{redline.rationale}\n\n"
        "Predict the counterparty's most likely pushback and draft one fallback clause."
    )
    return await llm.generate_structured(
        prompt=prompt, schema=NegotiationFallback, system_prompt=_SYSTEM_PROMPT
    )
