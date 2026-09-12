"""Ask agent — general legal-tech knowledge answers (GENERAL_LEGAL_TECH_QUESTION).

Not grounded in the tenant's own documents — answered from the model's own
knowledge, clearly labelled as such by the caller (app/agents/ask/pipeline.py
sets response type GENERAL_INFO). No fabricated portfolio citations.
"""

from __future__ import annotations

from app.llm import client as llm
from app.models.ask import GeneralLegalAnswer

_SYSTEM_PROMPT = (
    "You answer general legal-technology and data-privacy-regulation questions — "
    "e.g. explaining what a law or concept is, typical market practice, or general "
    "background on India's DPDP Act 2023 or the EU GDPR. This is general information, "
    "NOT specific to any particular contract or company, and NOT a substitute for "
    "advice from a qualified lawyer — say so if the question edges toward needing "
    "personalised legal advice. Keep answers concise and factual. Do not invent "
    "specific statute numbers, penalty amounts, or dates you are not confident about — "
    "say so plainly instead of guessing."
)


async def answer_general_question(question: str) -> GeneralLegalAnswer:
    return await llm.generate_structured(
        prompt=f"QUESTION:\n{question}",
        schema=GeneralLegalAnswer,
        system_prompt=_SYSTEM_PROMPT,
    )
