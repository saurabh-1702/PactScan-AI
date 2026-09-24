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
from app.api.access import owner_scope
from app.api.deps import CurrentUser, get_current_user, require_role
from app.db.postgres_client import get_db
from app.models.horizon_scanning import (
    AffectedContractRef,
    RegulationUpdateOut,
    SimulateUpdateRequest,
    SimulateUpdateResult,
)

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


_UPDATE_SECTION_PREFIX = "Amendment effective"


def _jurisdiction(regulation_name: str) -> str | None:
    """Derived from the regulation's name — the graph doesn't store one."""
    name = regulation_name.lower()
    if "dpdp" in name or "india" in name:
        return "India"
    if "gdpr" in name or "european" in name or "eu " in name:
        return "European Union"
    return None


@router.get("/updates", response_model=list[RegulationUpdateOut])
def list_updates(
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[RegulationUpdateOut]:
    """The regulatory-update log — readable by every role. Amendments come
    first, newest effective date first, then the baseline clauses. Each update
    lists the contracts (that this caller may see) it produced findings on."""
    owner = owner_scope(current_user)
    filenames = {
        c["contract_id"]: c["filename"]
        for c in store.list_contracts(tenant_id=current_user.tenant_id, owner_user_id=owner)
    }
    by_rule: dict[str, set[str]] = {}
    for f in store.get_all_findings(tenant_id=current_user.tenant_id, owner_user_id=owner):
        by_rule.setdefault(f["rule_or_regulation_violated"], set()).add(f["contract_id"])

    out: list[RegulationUpdateOut] = []
    for r in store.get_regulation_clauses():
        is_update = str(r.get("section") or "").startswith(_UPDATE_SECTION_PREFIX)
        affected: list[AffectedContractRef] = []
        if is_update:
            label = f"{r['regulation_name']} {r['section']} (update {r.get('effective_date')})"
            affected = [
                AffectedContractRef(contract_id=cid, filename=filenames[cid])
                for cid in sorted(by_rule.get(label, set()))
                if cid in filenames
            ]
        out.append(
            RegulationUpdateOut(
                id=r["id"],
                regulation_name=r["regulation_name"],
                jurisdiction=_jurisdiction(r["regulation_name"]),
                section=r.get("section") or "",
                text=r.get("text") or "",
                effective_date=r.get("effective_date"),
                kind="update" if is_update else "baseline",
                affected_contracts=affected,
            )
        )
    out.sort(
        key=lambda u: (
            0 if u.kind == "update" else 1,
            "" if u.kind != "update" else _neg(u.effective_date or ""),
            u.regulation_name,
            u.section,
        )
    )
    return out


def _neg(date_text: str) -> str:
    """Sort key that orders ISO-style date strings newest-first."""
    return "".join(chr(0x10FFFF - ord(ch)) for ch in date_text)
