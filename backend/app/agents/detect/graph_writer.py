"""Write an ingested contract into the knowledge graph.

Responsibilities:
* upsert the Contract node
* write every Clause node + BELONGS_TO edge
* detect OVERRIDES relationships (keyword heuristic + LLM confirmation) and write
  them, so a later clause can be read in light of the one it supersedes
"""

from __future__ import annotations

import logging

from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.llm import client as llm
from app.models.clause import ExtractedClause, OverrideCheckResult

logger = logging.getLogger("pactscan.detect.graph_writer")

# Heuristic triggers — a clause containing one of these *may* override another.
OVERRIDE_KEYWORDS = (
    "notwithstanding",
    "supersede",
    "supersedes",
    "superseding",
    "in lieu of",
    "prevail",
    "prevails",
    "takes precedence",
    "overrides",
    "amends",
    "amended",
    "for the avoidance of doubt",
    "to the extent of any conflict",
)

_OVERRIDE_SYSTEM_PROMPT = (
    "You determine whether one contract clause overrides, amends, or supersedes another. "
    "Answer strictly about legal effect: does Clause A change, limit, or replace the "
    "operation of Clause B (in whole or for a specific scope such as 'data-breach events')? "
    "If A merely references B without changing its effect, that is not an override."
)


def _may_override(clause: ExtractedClause) -> bool:
    text = clause.raw_text.lower()
    return any(kw in text for kw in OVERRIDE_KEYWORDS)


async def _confirm_override(
    candidate: ExtractedClause, target: ExtractedClause
) -> OverrideCheckResult:
    prompt = (
        f"Clause A (page {candidate.page_number}, '{candidate.section_header}'):\n"
        f"{candidate.raw_text}\n\n"
        f"Clause B (page {target.page_number}, '{target.section_header}'):\n"
        f"{target.raw_text}\n\n"
        "Does Clause A override, amend, or supersede Clause B? "
        "If yes, state the scope it applies to."
    )
    return await llm.generate_structured(
        prompt=prompt,
        schema=OverrideCheckResult,
        system_prompt=_OVERRIDE_SYSTEM_PROMPT,
    )


async def write_contract_graph(
    store: GraphStore,
    contract_id: str,
    filename: str,
    clauses: list[ExtractedClause],
    tenant_id: str = DEMO_TENANT,
) -> None:
    store.upsert_contract(contract_id, filename, tenant_id=tenant_id)
    for clause in clauses:
        store.add_clause(clause, tenant_id=tenant_id)

    # Override detection: for each keyword-flagged clause, ask the LLM which
    # other clause(s) of a compatible type it changes the effect of.
    for candidate in clauses:
        if not _may_override(candidate):
            continue
        for target in clauses:
            if target.clause_id == candidate.clause_id:
                continue
            # an override is asserted by a same-page or later provision against
            # an earlier (or same-page) one
            if target.page_number > candidate.page_number:
                continue
            if not _types_compatible(candidate, target):
                continue
            result = await _confirm_override(candidate, target)
            if result.overrides:
                store.add_override(
                    candidate.clause_id,
                    target.clause_id,
                    scope=result.scope,
                    tenant_id=tenant_id,
                )
                logger.info(
                    "OVERRIDES: %s (p%d) -> %s (p%d) scope=%r",
                    candidate.clause_id,
                    candidate.page_number,
                    target.clause_id,
                    target.page_number,
                    result.scope,
                )


def _types_compatible(a: ExtractedClause, b: ExtractedClause) -> bool:
    """An override usually concerns the same subject. Same clause_type is the
    strong signal; also allow a liability clause to be overridden by an SOW/
    addendum clause that the extractor labelled OTHER."""
    if a.clause_type == b.clause_type:
        return True
    from app.models.clause import ClauseType

    liability = {ClauseType.LIMITATION_OF_LIABILITY, ClauseType.INDEMNIFICATION}
    if b.clause_type in liability and a.clause_type in (liability | {ClauseType.OTHER}):
        return True
    return False
