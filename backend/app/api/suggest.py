"""Suggest agent API.

POST /api/suggest/from-finding/{finding_id}  -> Retriever + drafting chained
                                                  from an existing Detect finding
POST /api/suggest/standalone                  -> same pipeline, manually specified
                                                  clause + free-text change request

Both are draft-only: nothing here ever writes to a file. That is Phase 3,
gated by human approval.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.detect.graph_store import GraphStore, get_graph_store
from app.agents.suggest.pipeline import (
    SuggestInputError,
    suggest_from_finding,
    suggest_standalone,
)
from app.api.deps import CurrentUser, get_current_user
from app.db.postgres_client import get_db
from app.models.redline import StandaloneSuggestRequest, SuggestResult

logger = logging.getLogger("pactscan.api.suggest")

router = APIRouter(prefix="/api/suggest", tags=["suggest"])


def get_store() -> GraphStore:
    return get_graph_store()


@router.post("/from-finding/{finding_id}", response_model=SuggestResult)
async def suggest_from_finding_endpoint(
    finding_id: str,
    store: GraphStore = Depends(get_store),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SuggestResult:
    try:
        return await suggest_from_finding(store, db, finding_id, tenant_id=current_user.tenant_id)
    except SuggestInputError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Suggest pipeline failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/standalone", response_model=SuggestResult)
async def suggest_standalone_endpoint(
    body: StandaloneSuggestRequest,
    store: GraphStore = Depends(get_store),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> SuggestResult:
    try:
        return await suggest_standalone(
            store,
            db,
            body.contract_id,
            body.clause_id,
            body.change_request,
            tenant_id=current_user.tenant_id,
        )
    except SuggestInputError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except RuntimeError as exc:
        logger.exception("Suggest pipeline failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc
