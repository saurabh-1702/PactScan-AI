"""Suggest agent — Retriever.

Given a clause (via a Detect finding or a standalone request), gather everything
the drafting step needs: semantically related clauses (vector search across the
tenant's whole graph), the clause's direct OVERRIDES context, and the exact
violated-rule/regulation text. Read-only — no file, no graph write beyond
lazily backfilling missing embeddings.
"""

from __future__ import annotations

from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.agents.suggest.embed_clauses import ensure_embeddings_for_contract
from app.llm import client as llm
from app.models.clause import ExtractedClause, Finding
from app.models.redline import OverrideContext, RelatedClause, RetrievedContext

_NO_SPECIFIC_RULE = (
    "(No specific playbook rule or regulation was cited — this is a user-requested "
    "change, not a Detect finding.)"
)


async def retrieve_context(
    store: GraphStore,
    clause: ExtractedClause,
    change_request: str,
    finding: Finding | None = None,
    tenant_id: str = DEMO_TENANT,
    top_k: int = 5,
) -> RetrievedContext:
    # 1. keep embeddings current for this contract before searching
    await ensure_embeddings_for_contract(store, clause.contract_id, tenant_id=tenant_id)

    clause_embedding = clause.embedding
    if clause_embedding is None:
        refreshed = store.get_clause_by_id(clause.clause_id, tenant_id=tenant_id)
        clause_embedding = refreshed.embedding if refreshed else None
    if clause_embedding is None:
        clause_embedding = await llm.generate_embedding(clause.raw_text)
        store.set_clause_embedding(clause.clause_id, clause_embedding, tenant_id=tenant_id)

    # 2. vector search for semantically related clauses tenant-wide
    similar = store.vector_search_similar_clauses(
        clause_embedding, tenant_id=tenant_id, top_k=top_k, exclude_clause_id=clause.clause_id
    )
    related = [RelatedClause.model_validate(r) for r in similar]

    # 3. direct OVERRIDES relationship context (both directions)
    override_rows = store.get_override_relationships(clause.clause_id, tenant_id=tenant_id)
    override_context = [OverrideContext.model_validate(r) for r in override_rows]

    # 4. the exact violated rule/regulation text, if this clause was flagged by Detect
    label, text = _NO_SPECIFIC_RULE, _NO_SPECIFIC_RULE
    targets = store.get_compliance_targets(clause.clause_id, tenant_id=tenant_id)
    if targets:
        # prefer the target matching what the finding actually cites, if we have one
        chosen = targets[0]
        if finding is not None:
            for t in targets:
                if t["label"] in finding.rule_or_regulation_violated:
                    chosen = t
                    break
        label, text = chosen["label"], chosen["text"]
    elif finding is not None:
        # no stored compliance edge (e.g. the deterministic cross-document-override
        # finding) — fall back to the finding's own label/explanation
        label, text = finding.rule_or_regulation_violated, finding.explanation

    return RetrievedContext(
        clause_id=clause.clause_id,
        clause_raw_text=clause.raw_text,
        violated_rule_or_regulation_text=text,
        violated_rule_or_regulation_label=label,
        related_clauses=related,
        override_context=override_context,
        change_request=change_request,
    )
