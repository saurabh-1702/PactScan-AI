"""Ask agent — content retrieval for CONTRACT_QUESTION.

Adapts (does not literally reuse) Phase 2's Retriever: that Retriever starts
from one already-known flagged clause, which doesn't fit a free-text
question. This module reuses the actual shared infrastructure instead —
``generate_embedding``, ``vector_search_similar_clauses``, and the lazy
embedding backfill helpers from Phase 2's ``embed_clauses`` module.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.agents.suggest.embed_clauses import backfill_all, ensure_embeddings_for_contract
from app.config import settings
from app.llm import client as llm
from app.models.ask import DocumentScope


@dataclass
class AskRetrievedItem:
    document_name: str
    page_number: int  # 0 for a regulation citation (not paginated)
    text: str
    similarity: float = 1.0


@dataclass
class RetrievalResult:
    items: list[AskRetrievedItem] = field(default_factory=list)
    abstain: bool = False
    abstain_reason: str = ""


def _normalize(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


# Generic words that appear in nearly every filename in this domain and would
# otherwise inflate a token-overlap score without actually identifying which
# document is meant (e.g. "contract" alone matching every fixture).
_GENERIC_NAME_TOKENS = {"contract", "agreement", "document", "the", "vendor", "dpa", "msa", "pdf", "doc", "docx"}


def find_contract_by_name(
    store: GraphStore,
    name_query: str,
    tenant_id: str = DEMO_TENANT,
    owner_user_id: str | None = None,
) -> dict | None:
    """Substring + word-overlap heuristic — deliberately simple, not a real
    fuzzy-matching library. Swap for rapidfuzz/difflib if this proves too
    weak once tested against real filenames."""
    q = _normalize(name_query or "")
    if not q:
        return None
    q_tokens = set(q.split()) - _GENERIC_NAME_TOKENS

    # list_contracts() returns most-recently-uploaded first, and the `>`
    # below keeps the first tied match — so when a tenant has uploaded the
    # same filename more than once, this resolves to the newest one.
    best, best_score = None, 0.0
    for c in store.list_contracts(tenant_id=tenant_id, owner_user_id=owner_user_id):
        name = _normalize(Path(c["filename"]).stem)
        if not name:
            continue
        if q == name:
            score = 1.0
        else:
            name_tokens = set(name.split()) - _GENERIC_NAME_TOKENS
            overlap = q_tokens & name_tokens
            score = len(overlap) / max(len(name_tokens), 1) if overlap else 0.0
        if score > best_score:
            best, best_score = c, score
    return best if best_score >= 0.5 else None


async def retrieve_for_content_question(
    store: GraphStore,
    question: str,
    document_scope: DocumentScope,
    mentioned_document_name: str | None,
    tenant_id: str = DEMO_TENANT,
    owner_user_id: str | None = None,
) -> RetrievalResult:
    contract_id = None
    allowed_ids: set[str] | None = None
    if owner_user_id is not None:
        # end_user: the portfolio is only the contracts they uploaded
        allowed_ids = {
            c["contract_id"]
            for c in store.list_contracts(tenant_id=tenant_id, owner_user_id=owner_user_id)
        }
    if document_scope == DocumentScope.SINGLE:
        match = find_contract_by_name(
            store, mentioned_document_name or "", tenant_id=tenant_id, owner_user_id=owner_user_id
        )
        if match is None:
            label = mentioned_document_name or "that document"
            return RetrievalResult(
                abstain=True,
                abstain_reason=f"I don't have a document matching {label!r} in your portfolio.",
            )
        contract_id = match["contract_id"]
        await ensure_embeddings_for_contract(store, contract_id, tenant_id=tenant_id)
    else:
        await backfill_all(store, tenant_id=tenant_id)

    embedding = await llm.generate_embedding(question)
    hits = store.vector_search_similar_clauses(
        embedding,
        tenant_id=tenant_id,
        top_k=settings.ask_top_k,
        contract_id=contract_id,
        allowed_contract_ids=allowed_ids,
    )

    if not hits or hits[0]["similarity"] < settings.ask_similarity_threshold:
        return RetrievalResult(
            abstain=True,
            abstain_reason="I don't have information about that in your contract portfolio.",
        )

    filenames = {c["contract_id"]: c["filename"] for c in store.list_contracts(tenant_id=tenant_id)}
    items = [
        AskRetrievedItem(
            document_name=filenames.get(h["contract_id"], h["contract_id"]),
            page_number=h.get("page_number") or 0,
            text=h["raw_text"],
            similarity=h["similarity"],
        )
        for h in hits
    ]

    # Always fold in the (small, ~5-item) seeded regulation text — cheap, and
    # guarantees a real citation for "what does DPDP/GDPR require" questions
    # rather than relying on vector search to surface it.
    for reg in store.get_regulation_clauses():
        items.append(
            AskRetrievedItem(
                document_name=f"{reg['regulation_name']} — {reg['section']}",
                page_number=0,
                text=reg["text"],
                similarity=1.0,
            )
        )

    return RetrievalResult(items=items, abstain=False)
