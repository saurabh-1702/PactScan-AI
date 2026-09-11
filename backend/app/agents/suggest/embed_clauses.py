"""Clause embeddings for the Suggest agent's vector retrieval.

Embeddings are generated lazily (``ensure_embeddings_for_contract``, called by
the Retriever before every vector search) so they never go stale as new
contracts are ingested. ``backfill_all`` is the one-time sweep for whatever
clauses already exist tenant-wide (e.g. the Phase 1 sample contracts).
"""

from __future__ import annotations

import logging

from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.llm import client as llm

logger = logging.getLogger("pactscan.suggest.embed")


async def ensure_embeddings_for_contract(
    store: GraphStore, contract_id: str, tenant_id: str = DEMO_TENANT
) -> int:
    """Embed any clause of this contract that doesn't have one yet. Returns the
    number of clauses embedded."""
    missing = store.get_clauses_missing_embedding(tenant_id=tenant_id, contract_id=contract_id)
    for clause in missing:
        embedding = await llm.generate_embedding(clause.raw_text)
        store.set_clause_embedding(clause.clause_id, embedding, tenant_id=tenant_id)
    if missing:
        logger.info("Embedded %d clause(s) for contract %s", len(missing), contract_id)
    return len(missing)


async def backfill_all(store: GraphStore, tenant_id: str = DEMO_TENANT) -> int:
    """One-time sweep: embed every clause tenant-wide that's missing one."""
    missing = store.get_clauses_missing_embedding(tenant_id=tenant_id)
    for clause in missing:
        embedding = await llm.generate_embedding(clause.raw_text)
        store.set_clause_embedding(clause.clause_id, embedding, tenant_id=tenant_id)
    logger.info("Backfilled embeddings for %d clause(s) (tenant=%s)", len(missing), tenant_id)
    store.ensure_vector_index()
    return len(missing)


if __name__ == "__main__":
    import asyncio

    from app.agents.detect.graph_store import get_graph_store

    async def _main():
        count = await backfill_all(get_graph_store())
        print(f"Embedded {count} clause(s).")

    asyncio.run(_main())
