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
        tier="cost_effective",
        version="latest",
        upload_file=file_from_path(str(path)),
        output_options={"markdown": True, "include_page_breaks": True},
    )
    return _parsed_document_from_llama_result(path.name, result)


def _parsed_document_from_llama_result(filename: str, result: object) -> ParsedDocument:
    """Best-effort extraction of per-page markdown from a ParsingGetResponse.

    The llama-cloud response shape has changed across versions; try the known
    locations in order and fail loudly if none match (so a real break surfaces
    during live testing rather than silently producing an empty document).
    """
    candidates = []
    for attr_chain in (("result", "pages"), ("pages",), ("data", "pages")):
        obj = result
        for attr in attr_chain:
            obj = getattr(obj, attr, None) if not isinstance(obj, dict) else obj.get(attr)
            if obj is None:
                break
        if obj:
            candidates = obj
            break

    if not candidates:
        raise RuntimeError(
            f"Could not locate per-page content in LlamaParse response of type {type(result)!r}. "
            "The llama-cloud API shape may have changed — inspect the response and update "
            "_parsed_document_from_llama_result()."
        )

    pages: list[ParsedPage] = []
    for i, page in enumerate(candidates, start=1):
        text = (
            _get(page, "md")
            or _get(page, "markdown")
            or _get(page, "text")
            or _get(page, "content")
            or ""
        )
        page_no = _get(page, "page") or _get(page, "page_number") or i
        pages.append(ParsedPage(page_number=int(page_no), text=str(text)))
    return ParsedDocument(filename=filename, pages=pages)


def _get(obj: object, key: str):
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
