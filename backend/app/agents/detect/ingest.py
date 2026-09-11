"""Ingestion pipeline: raw contract file -> parsed pages -> extracted clauses.

Document parsing uses LlamaParse via the current ``llama-cloud`` package
(``client.parsing.parse``). Clause extraction goes through the provider-agnostic
LLM abstraction (``app.llm.client``) — never a Gemini client directly.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from app.config import settings
from app.llm import client as llm
from app.models.clause import (
    ClauseExtractionResult,
    ConfidenceLevel,
    ExtractedClause,
)

logger = logging.getLogger("pactscan.detect.ingest")


@dataclass
class ParsedPage:
    page_number: int
    text: str
    section_headers: list[str] = field(default_factory=list)


@dataclass
class ParsedDocument:
    filename: str
    pages: list[ParsedPage]

    def as_prompt_text(self) -> str:
        blocks = []
        for p in self.pages:
            blocks.append(f"===== PAGE {p.page_number} =====\n{p.text.strip()}")
        return "\n\n".join(blocks)


# --------------------------------------------------------------------------- #
# LlamaParse
# --------------------------------------------------------------------------- #
def parse_document(file_path: str | Path) -> ParsedDocument:
    """Parse a contract file into per-page, layout-aware markdown text."""
    path = Path(file_path)
    if not settings.llama_cloud_api_key or settings.llama_cloud_api_key == "your_key_here":
        raise RuntimeError(
            "LLAMA_CLOUD_API_KEY is not set in backend\\.env — required for document parsing."
        )

    from llama_cloud import LlamaCloud, file_from_path

    client = LlamaCloud(api_key=settings.llama_cloud_api_key)
    result = client.parsing.parse(
        tier=settings.llama_parse_tier,
        version="latest",
        upload_file=file_from_path(str(path)),
        expand=["markdown"],
    )
    return _parsed_document_from_llama_result(path.name, result)


def _parsed_document_from_llama_result(filename: str, result: object) -> ParsedDocument:
    """Extract per-page markdown from a llama-cloud ParsingGetResponse.

    Shape (llama-cloud >= 2.x): result.markdown.pages -> list of page objects,
    each with .markdown / .page_number (successful) or .error (failed).
    Falls back to result.text.pages, then markdown_full / text_full.
    """
    job_status = _get(_get(result, "job"), "status")

    md = _get(result, "markdown")
    md_pages = _get(md, "pages") if md is not None else None
    if md_pages:
        pages = []
        for i, page in enumerate(md_pages, start=1):
            content = _get(page, "markdown") or _get(page, "error") or ""
            page_no = _get(page, "page_number") or i
            header = _get(page, "header")
            pages.append(
                ParsedPage(
                    page_number=int(page_no),
                    text=str(content),
                    section_headers=[header] if header else [],
                )
            )
        return ParsedDocument(filename=filename, pages=pages)

    txt = _get(result, "text")
    txt_pages = _get(txt, "pages") if txt is not None else None
    if txt_pages:
        pages = [
            ParsedPage(
                page_number=int(_get(p, "page_number") or i),
                text=str(_get(p, "text") or ""),
            )
            for i, p in enumerate(txt_pages, start=1)
        ]
        return ParsedDocument(filename=filename, pages=pages)

    whole = _get(result, "markdown_full") or _get(result, "text_full")
    if whole:
        return ParsedDocument(
            filename=filename, pages=[ParsedPage(page_number=1, text=str(whole))]
        )

    raise RuntimeError(
        f"LlamaParse returned no usable content (job status={job_status!r}, "
        f"response type={type(result)!r}). Inspect the response and update "
        "_parsed_document_from_llama_result()."
    )


def _get(obj: object, key: str):
    if obj is None:
        return None
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


# --------------------------------------------------------------------------- #
# Clause extraction (LLM)
# --------------------------------------------------------------------------- #
_EXTRACTION_SYSTEM_PROMPT = (
    "You are a contract-analysis assistant for a vendor Data Processing Agreement "
    "compliance tool. Extract distinct legal clauses from the contract text. For each "
    "clause, choose the single best clause_type from the allowed taxonomy. If a clause "
    "does not clearly fit any category, use OTHER and set confidence to 'low'. If you are "
    "unsure about a clause's type, set confidence to 'low' — never guess with high "
    "confidence. Preserve the exact page number each clause appears on and its nearest "
    "section header. Return every clause you find; do not summarise or merge unrelated clauses."
)


async def extract_clauses(
    parsed: ParsedDocument, contract_id: str
) -> list[ExtractedClause]:
    prompt = (
        "Extract the clauses from the following vendor contract. The text is delimited "
        "by page markers; use them to record each clause's page_number.\n\n"
        f"{parsed.as_prompt_text()}"
    )
    result = await llm.generate_structured(
        prompt=prompt,
        schema=ClauseExtractionResult,
        system_prompt=_EXTRACTION_SYSTEM_PROMPT,
    )

    clauses: list[ExtractedClause] = []
    for lc in result.clauses:
        clauses.append(
            ExtractedClause(
                clause_id=f"cl_{uuid.uuid4().hex[:12]}",
                contract_id=contract_id,
                clause_type=lc.clause_type,
                page_number=lc.page_number,
                section_header=lc.section_header or "(unlabelled)",
                raw_text=lc.raw_text,
                confidence=lc.confidence or ConfidenceLevel.low,
            )
        )
    if not clauses:
        logger.warning("Clause extraction returned zero clauses for %s", contract_id)
    return clauses
