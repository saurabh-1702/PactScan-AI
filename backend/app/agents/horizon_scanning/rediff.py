"""Horizon-Scanning (Phase 6) — the re-diff engine.

Given a newly-added RegulationClause, finds every existing Clause across
every contract already in the system that's topically related (reusing
Phase 2's portfolio-wide vector similarity search), runs the same
NLI-style compliance check Phase 1's Detect Agent uses, and turns any
CONTRADICTS or mandatory-gap NEUTRAL result into a Finding via the exact
same finding-creation helper Detect uses (``build_finding_from_nli``) —
so a Horizon-Scanning finding and a Detect finding are structurally
indistinguishable in storage. Each newly-created finding fires Phase 5's
notification hook exactly as a normal Detect finding would.

Deliberately additive: uses ``GraphStore.add_findings`` (never
``replace_findings``), since a contract already Detect-scanned must not
lose its original findings just because a later regulation update
re-diffed it.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.agents.detect.detect_agent import build_finding_from_nli
from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.agents.notifications.notify import notify_new_findings
from app.agents.suggest.embed_clauses import backfill_all
from app.config import settings
from app.llm import client as llm
from app.models.clause import Finding, NLILabel, NLIResult

logger = logging.getLogger("pactscan.horizon_scanning.rediff")

_NLI_SYSTEM_PROMPT = (
    "You perform natural-language inference for contract-compliance review. You are "
    "given ONE existing contract clause and ONE new-or-amended regulation requirement. "
    "Classify the clause against the requirement:\n"
    "  ENTAILS     - the clause affirmatively satisfies this requirement\n"
    "  CONTRADICTS - the clause affirmatively permits or requires something this "
    "requirement forbids, OR it governs exactly this requirement's subject but omits "
    "a protection the requirement makes mandatory\n"
    "  NEUTRAL     - the clause simply does not deal with this requirement's subject\n"
    "Be conservative. A clause that is merely silent on an adjacent obligation is "
    "NEUTRAL, not CONTRADICTS. Only use CONTRADICTS when the clause itself creates the "
    "compliance problem."
)


async def _classify_single(clause_text: str, requirement_text: str) -> NLIResult:
    prompt = (
        f"EXISTING CLAUSE:\n{clause_text}\n\n"
        f"NEW/AMENDED REGULATION REQUIREMENT:\n{requirement_text}\n\n"
        "Classify the clause against this requirement."
    )
    return await llm.generate_structured(
        prompt=prompt, schema=NLIResult, system_prompt=_NLI_SYSTEM_PROMPT
    )


async def rediff_regulation_update(
    store: GraphStore,
    db: Session,
    new_clause: dict,
    tenant_id: str = DEMO_TENANT,
) -> dict:
    """Returns a summary: {contracts_flagged, findings_created, details:
    [{contract_id, filename, new_finding_ids}]}."""
    # Detect never embeds a contract's clauses itself — embedding is lazy,
    # only ever triggered by Suggest/Ask so far. A contract Detect-scanned
    # but never touched by either would have zero embedded clauses and thus
    # zero vector-index hits, no matter how relevant the new regulation
    # clause actually is. Same fix Ask's portfolio-question path already
    # needed (app/agents/ask/ask_retriever.py) for the identical reason.
    await backfill_all(store, tenant_id=tenant_id)
    embedding = await llm.generate_embedding(new_clause["text"])
    hits = store.vector_search_similar_clauses(
        embedding, tenant_id=tenant_id, top_k=settings.horizon_scan_top_k, contract_id=None
    )
    relevant = [h for h in hits if h["similarity"] >= settings.horizon_scan_similarity_threshold]

    rule_label = f"{new_clause['regulation_name']} {new_clause['section']} (update {new_clause['effective_date']})"
    rule_id = f"horizon:{new_clause['id']}"

    findings_by_contract: dict[str, list[Finding]] = {}
    for hit in relevant:
        clause = store.get_clause_by_id(hit["clause_id"], tenant_id=tenant_id)
        if clause is None:
            continue  # stale hit; clause was removed since the index was built
        nli = await _classify_single(clause.raw_text, new_clause["text"])
        if nli.label == NLILabel.ENTAILS:
            continue  # already compliant with the new requirement — no finding
        finding = build_finding_from_nli(
            contract_id=clause.contract_id,
            clause=clause,
            override_chain=[],
            nli=nli,
            rule_id=rule_id,
            rule_label=rule_label,
            kind="regulation",
        )
        findings_by_contract.setdefault(clause.contract_id, []).append(finding)

    contracts = {c["contract_id"]: c for c in store.list_contracts(tenant_id=tenant_id)}
    filenames = {cid: c["filename"] for cid, c in contracts.items()}

    details: list[dict] = []
    total_new = 0
    for contract_id, findings in findings_by_contract.items():
        new = store.add_findings(contract_id, findings, tenant_id=tenant_id)
        if not new:
            continue  # this simulated update was already re-diffed against this contract
        filename = filenames.get(contract_id, contract_id)
        notify_new_findings(
            db,
            tenant_id,
            filename,
            new,
            contract_owner_user_id=contracts.get(contract_id, {}).get("uploaded_by_user_id"),
        )
        total_new += len(new)
        details.append(
            {
                "contract_id": contract_id,
                "filename": filename,
                "new_finding_ids": [f.finding_id for f in new],
            }
        )

    logger.info(
        "Horizon-Scanning update %s flagged %d contract(s), %d new finding(s)",
        new_clause["id"],
        len(details),
        total_new,
    )
    return {"contracts_flagged": len(details), "findings_created": total_new, "details": details}
