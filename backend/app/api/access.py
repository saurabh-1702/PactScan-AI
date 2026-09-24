"""Contract-ownership scoping (Phase 6b).

An end_user only ever sees contracts they uploaded themselves; reviewers and
admins see every contract in their tenant. Tenant isolation (Phase 5) stays
the outer wall — this is a second, narrower wall inside it, and applies only
to end_user.

Every endpoint that reads or acts on a contract goes through one of these
helpers rather than re-deriving the rule, so it can't drift between the
dashboard, approvals, documents, restore, Ask, and Suggest.
"""

from __future__ import annotations

from fastapi import HTTPException

from app.agents.detect.graph_store import GraphStore
from app.api.deps import CurrentUser


def owner_scope(user: CurrentUser) -> str | None:
    """The uploader id to filter by, or None for an unrestricted (tenant-wide)
    view — i.e. reviewers and admins."""
    return user.user_id if user.role == "end_user" else None


def visible_contract_ids(store: GraphStore, user: CurrentUser) -> set[str] | None:
    """Contract ids this user may see, or None meaning no restriction."""
    owner = owner_scope(user)
    if owner is None:
        return None
    return {
        c["contract_id"]
        for c in store.list_contracts(tenant_id=user.tenant_id, owner_user_id=owner)
    }


def ensure_contract_access(store: GraphStore, user: CurrentUser, contract_id: str) -> None:
    """404 (not 403, so the id's existence isn't revealed) if an end_user asks
    about a contract someone else uploaded."""
    allowed = visible_contract_ids(store, user)
    if allowed is not None and contract_id not in allowed:
        raise HTTPException(404, f"contract {contract_id!r} not found")
