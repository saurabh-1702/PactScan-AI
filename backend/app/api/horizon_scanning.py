"""Horizon-Scanning API (Phase 6).

POST /api/horizon-scanning/simulate-update -> admin-only. Simulates a new or
amended regulation clause landing, then re-diffs it against every clause
already in the tenant's portfolio.

Honesty note: real 24/7 monitoring against government regulatory feeds is
out of scope for this build. This is the mechanism a real scheduler would
call — triggered manually here rather than on a timer. The frontend surfaces
this same note to the admin triggering it.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.agents.detect.graph_store import GraphStore, get_graph_store
from app.agents.horizon_scanning.regulation_writer import add_regulation_update
from app.agents.horizon_scanning.rediff import rediff_regulation_update
from app.api.deps import CurrentUser, require_role
from app.db.postgres_client import get_db
from app.models.horizon_scanning import SimulateUpdateRequest, SimulateUpdateResult

logger = logging.getLogger("pactscan.api.horizon_scanning")

router = APIRouter(prefix="/api/horizon-scanning", tags=["horizon-scanning"])


def get_store() -> GraphStore:
    return get_graph_store()


@router.post("/simulate-update", response_model=SimulateUpdateResult)
async def simulate_update(
    body: SimulateUpdateRequest,
    store: GraphStore = Depends(get_store),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(require_role(["admin"])),
) -> SimulateUpdateResult:
    try:
        new_clause = add_regulation_update(
            store, body.regulation_name, body.new_clause_text, body.effective_date
        )
        summary = await rediff_regulation_update(
            store, db, new_clause, tenant_id=current_user.tenant_id
        )
    except RuntimeError as exc:
        logger.exception("Horizon-Scanning simulate-update failed")
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return SimulateUpdateResult(regulation_clause_id=new_clause["id"], **summary)
