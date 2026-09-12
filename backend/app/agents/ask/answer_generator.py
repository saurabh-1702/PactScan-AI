"""Ask agent — answer generation for CONTRACT_QUESTION.

Every factual claim must cite a source; the model's self-reported ``sources``
are validated against what was actually retrieved before being trusted — any
citation naming a document that wasn't part of the retrieved context is
dropped, never passed through, consistent with the project's abstain-rather-
than-guess grounding rule (Section 12.8 of the project spec).
"""

from __future__ import annotations

from app.agents.ask.ask_retriever import AskRetrievedItem
from app.llm import client as llm
from app.models.ask import AskAnswer

_SYSTEM_PROMPT = (
    "You answer questions about a company's vendor contract portfolio using ONLY the "
    "provided excerpts — never information from outside them. Every factual claim in "
    "your answer must cite the source document name and page number it came from "
    "(inline, e.g. '(Acme_MSA.pdf, page 3)'). If multiple documents are relevant, "
    "clearly attribute which claim comes from which document. Regulation excerpts are "
    "cited by their regulation name and section instead of a page number. "
    "If the excerpts genuinely don't answer the question, say so honestly in "
    "answer_text rather than guessing, and return an empty sources list. Populate the "
    "structured `sources` field with exactly the (document_name, page_number) pairs "
    "you actually cited in the text."
)


def _excerpt_block(items: list[AskRetrievedItem]) -> str:
    return "\n\n".join(
        f"[{it.document_name}, page {it.page_number}] {it.text}" for it in items
    )


async def generate_answer(question: str, items: list[AskRetrievedItem]) -> AskAnswer:
    prompt = (
        f"QUESTION:\n{question}\n\n"
        f"RELEVANT EXCERPTS FROM THE CONTRACT PORTFOLIO:\n{_excerpt_block(items)}\n\n"
        "Answer the question, citing sources."
    )
    answer = await llm.generate_structured(prompt=prompt, schema=AskAnswer, system_prompt=_SYSTEM_PROMPT)

    # Defense in depth: never pass through a citation to a document that
    # wasn't actually part of the retrieved context.
    valid_names = {it.document_name for it in items}
    answer.sources = [s for s in answer.sources if s.document_name in valid_names]
    return answer
