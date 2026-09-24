"""Contract list — the "my documents" view.

GET /api/contracts -> every contract the caller may see (an end_user: their
own uploads; a reviewer/admin: the whole tenant), newest first, with finding
counts and version count. Read-only; feeds the dashboard's recent documents,
Detect's document picker and the command palette.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.agents.detect.graph_store import GraphStore, get_graph_store
from app.api.access import owner_scope
from app.api.deps import CurrentUser, get_current_user
from app.db.models import DocumentVersion, User
from app.db.postgres_client import get_db
from app.models.contracts import ContractSummary

router = APIRouter(prefix="/api/contracts", tags=["contracts"])


def get_store() -> GraphStore:
    return get_graph_store()


@router.get("", response_model=list[ContractSummary])
def list_contracts(
    db: Session = Depends(get_db),
    store: GraphStore = Depends(get_store),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[ContractSummary]:
    owner = owner_scope(current_user)
    contracts = store.list_contracts(tenant_id=current_user.tenant_id, owner_user_id=owner)

    counts: dict[str, dict[str, int]] = {}
    for f in store.get_all_findings(tenant_id=current_user.tenant_id, owner_user_id=owner):
        bucket = counts.setdefault(f["contract_id"], {"HIGH": 0, "MEDIUM": 0, "LOW": 0})
        bucket[f["severity"]] = bucket.get(f["severity"], 0) + 1

    versions = dict(
        db.query(DocumentVersion.contract_id, func.count(DocumentVersion.id))
        .filter(DocumentVersion.tenant_id == current_user.tenant_id)
        .group_by(DocumentVersion.contract_id)
        .all()
    )
    emails = {
        u.id: u.email for u in db.query(User).filter(User.tenant_id == current_user.tenant_id).all()
    }

    out: list[ContractSummary] = []
    for c in contracts:
        sev = counts.get(c["contract_id"], {})
        out.append(
            ContractSummary(
                contract_id=c["contract_id"],
                filename=c["filename"],
                uploaded_by_user_id=c.get("uploaded_by_user_id"),
                uploaded_by_email=emails.get(c.get("uploaded_by_user_id") or ""),
                uploaded_at=c.get("upload_date"),
                high=sev.get("HIGH", 0),
                medium=sev.get("MEDIUM", 0),
                low=sev.get("LOW", 0),
                total_findings=sum(sev.values()),
                version_count=versions.get(c["contract_id"], 0),
            )
        )
    return out
