"""Suggest agent — adversarial review (Contrarian + Judge).

Contrarian argues the original clause is actually defensible from the
counterparty's perspective; Judge reconciles that against the original
finding's reasoning into a final, confidence-scored verdict. A "dismissed"
verdict is still returned and persisted — never silently dropped — so the
adversarial check stays auditable (Section 3.1 of the project spec).
"""

from __future__ import annotations

from app.llm import client as llm
from app.models.redline import ContrarianArgument, JudgeVerdict, RetrievedContext

_CONTRARIAN_SYSTEM_PROMPT = (
    "You represent the counterparty (the vendor) in a contract review. Given a "
    "clause that the client's compliance tool has flagged as a problem, construct "
    "the strongest good-faith argument that the clause is actually fine, standard, "
    "or defensible as written — from the vendor's perspective. Do not fabricate "
    "facts not present in the material. If you genuinely cannot construct a "
    "reasonable defence, say so plainly rather than inventing a weak one."
)

_JUDGE_SYSTEM_PROMPT = (
    "You are a neutral senior reviewer. You are given (1) the original compliance "
    "finding and why the clause was flagged, and (2) the counterparty's strongest "
    "counter-argument for why the clause is actually fine. Decide whether the "
    "finding is 'confirmed' (the original concern stands), 'downgraded' (some "
    "merit to the counter-argument, but a residual concern remains — lower the "
    "confidence but do not dismiss it), or 'dismissed' (the counter-argument is "
    "correct and the finding is not actually a compliance problem). Always give a "
    "final_confidence between 0 and 100 and a concrete reasoning that would let a "
    "human reviewer see how you reached this verdict."
)


async def run_contrarian(ctx: RetrievedContext) -> ContrarianArgument:
    prompt = (
        f"FLAGGED CLAUSE:\n{ctx.clause_raw_text}\n\n"
        f"WHY IT WAS FLAGGED:\n{ctx.violated_rule_or_regulation_label}\n"
        f"{ctx.violated_rule_or_regulation_text}\n\n"
        "Construct the vendor's strongest defence of this clause."
    )
    return await llm.generate_structured(
        prompt=prompt, schema=ContrarianArgument, system_prompt=_CONTRARIAN_SYSTEM_PROMPT
    )


async def run_judge(
    ctx: RetrievedContext, original_confidence: int, contrarian: ContrarianArgument
) -> JudgeVerdict:
    prompt = (
        f"ORIGINAL FINDING REASONING (confidence {original_confidence}):\n"
        f"{ctx.violated_rule_or_regulation_label}: {ctx.change_request}\n\n"
        f"COUNTERPARTY'S COUNTER-ARGUMENT (their confidence {contrarian.confidence}):\n"
        f"{contrarian.argument}\n"
        f"Strongest point: {contrarian.strongest_point}\n\n"
        "Render your verdict."
    )
    return await llm.generate_structured(
        prompt=prompt, schema=JudgeVerdict, system_prompt=_JUDGE_SYSTEM_PROMPT
    )
