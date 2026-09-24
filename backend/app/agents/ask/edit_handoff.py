"""Ask agent — chat-triggered edit requests (EDIT_INSTRUCTION).

This is a new *entry point* into Phase 2's Suggest pipeline, not a new write
path: it calls ``suggest_standalone`` exactly as the /api/suggest/standalone
endpoint does, which already auto-creates a pending Approval (Phase 3). This
function never touches the Executor and never writes a file — it can only
ever produce a draft sitting in the same approval queue as every other
redline in the system.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.agents.ask.ask_retriever import find_contract_by_name
from app.agents.detect.graph_store import DEMO_TENANT, GraphStore
from app.agents.suggest.embed_clauses import ensure_embeddings_for_contract
from app.agents.suggest.pipeline import SuggestInputError, suggest_standalone
from app.db.models import Approval
from app.llm import client as llm
from app.models.ask import AskResponse, AskResponseType, ScopeClassification


async def handle_edit_instruction(
    store: GraphStore,
    db: Session,
    classification: ScopeClassification,
    tenant_id: str = DEMO_TENANT,
    requested_by_user_id: str | None = None,
    owner_user_id: str | None = None,
) -> AskResponse:
    name = classification.mentioned_document_name
    match = (
        find_contract_by_name(store, name or "", tenant_id=tenant_id, owner_user_id=owner_user_id)
        if name
        else None
    )
    if match is None:
        msg = (
            f"I don't have a document matching {name!r} in your portfolio."
            if name
            else "I couldn't tell which document you want edited — please name it."
        )
        return AskResponse(session_id="", type=AskResponseType.ABSTAINED, answer_text=msg)

    contract_id = match["contract_id"]
    change_request = classification.requested_change or "Apply the requested change."

    # a target clause_id is required by suggest_standalone — pick the clause
    # most relevant to the requested change via the same vector search used
    # everywhere else in Ask/Suggest.
    await ensure_embeddings_for_contract(store, contract_id, tenant_id=tenant_id)
    embedding = await llm.generate_embedding(change_request)
    hits = store.vector_search_similar_clauses(
        embedding, tenant_id=tenant_id, top_k=1, contract_id=contract_id
    )
    if not hits:
        return AskResponse(
            session_id="",
            type=AskResponseType.ABSTAINED,
            answer_text=(
                f"I found {match['filename']} but it has no clauses on file yet — "
                "run Detect on it first."
            ),
        )
    clause_id = hits[0]["clause_id"]

    try:
        result = await suggest_standalone(
            store,
            db,
            contract_id,
            clause_id,
            change_request,
            tenant_id=tenant_id,
            requested_by_user_id=requested_by_user_id,
        )
    except SuggestInputError as exc:
        return AskResponse(session_id="", type=AskResponseType.ABSTAINED, answer_text=str(exc))

    approval = (
        db.query(Approval)
        .filter(Approval.redline_suggestion_id == result.suggestion_id)
        .order_by(Approval.created_at.desc())
        .first()
    )

    return AskResponse(
        session_id="",
        type=AskResponseType.EDIT_DRAFT,
        answer_text=(
            f"I've drafted a proposed edit to {match['filename']} and added it to the "
            "approval queue. This is a DRAFT only — nothing has changed in the real "
            "document. A human reviewer must approve it before anything is written."
        ),
        sources=[],
        suggestion_id=result.suggestion_id,
        approval_id=approval.id if approval else None,
    )
