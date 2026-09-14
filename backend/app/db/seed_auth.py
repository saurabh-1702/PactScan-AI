"""Idempotent startup seeding for Phase 5's tenant/user tables — same pattern
as app.agents.detect.seed_data.seed() for the Neo4j playbook/regulations.

Seeds the one tenant every prior phase hardcoded (DEMO_TENANT) plus two demo
accounts so role-gating can be demonstrated immediately without a manual
POST /api/auth/register round-trip. Credentials are documented in
docs/README.md.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.agents.detect.graph_store import DEMO_TENANT
from app.core.security import hash_password
from app.db.models import Tenant, User

logger = logging.getLogger("pactscan.db.seed_auth")

DEMO_END_USER_EMAIL = "enduser@demo.pactscan.ai"
DEMO_REVIEWER_EMAIL = "reviewer@demo.pactscan.ai"
DEMO_PASSWORD = "PactScanDemo123!"


def seed_demo_tenant_and_users(db: Session) -> None:
    if db.get(Tenant, DEMO_TENANT) is None:
        db.add(Tenant(id=DEMO_TENANT, name="Demo Tenant"))
        db.commit()
        logger.info("Seeded tenant %r", DEMO_TENANT)

    _seed_user(db, DEMO_END_USER_EMAIL, "end_user")
    _seed_user(db, DEMO_REVIEWER_EMAIL, "reviewer")


def _seed_user(db: Session, email: str, role: str) -> None:
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        return
    db.add(
        User(
            tenant_id=DEMO_TENANT,
            email=email,
            hashed_password=hash_password(DEMO_PASSWORD),
            role=role,
        )
    )
    db.commit()
    logger.info("Seeded demo user %s (role=%s)", email, role)
