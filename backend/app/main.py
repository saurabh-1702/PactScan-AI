"""FastAPI application entrypoint.

Phase 0 scaffold: a health endpoint plus a non-fatal startup check that logs
whether Neo4j and Postgres are reachable. The app must still start even when the
databases are down — this phase is about scaffolding, not real connections.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.db import neo4j_client, postgres_client

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("pactscan")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # --- Neo4j ---
    try:
        neo4j_client.verify_connectivity()
        logger.info("Neo4j connection OK (%s)", settings.neo4j_uri)
    except Exception as exc:  # noqa: BLE001 - scaffold: log, don't crash
        logger.warning("Neo4j unreachable at %s: %s", settings.neo4j_uri, exc)

    # --- Postgres ---
    try:
        postgres_client.verify_connectivity()
        logger.info("PostgreSQL connection OK")
    except Exception as exc:  # noqa: BLE001 - scaffold: log, don't crash
        logger.warning("PostgreSQL unreachable: %s", exc)

    # --- Seed playbook + regulations (idempotent) ---
    try:
        from app.agents.detect.graph_store import get_graph_store
        from app.agents.detect.seed_data import seed

        seed(get_graph_store())
    except Exception as exc:  # noqa: BLE001 - non-fatal: dashboard/detect degrade gracefully
        logger.warning("Playbook/regulation seeding skipped: %s", exc)

    # --- Create application tables (idempotent; no migration framework yet) ---
    try:
        from app.db import models as _db_models  # noqa: F401 - registers tables on Base
        from app.db.postgres_client import Base, engine

        Base.metadata.create_all(bind=engine)
        logger.info("PostgreSQL tables ensured (redline_suggestions, ...)")
    except Exception as exc:  # noqa: BLE001 - non-fatal: degrades gracefully like Neo4j seeding
        logger.warning("PostgreSQL table creation skipped: %s", exc)

    yield

    neo4j_client.close_driver()


app = FastAPI(title="PactScan AI", version="0.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from app.api.approvals import router as approvals_router  # noqa: E402
from app.api.ask import router as ask_router  # noqa: E402
from app.api.detect import router as detect_router  # noqa: E402
from app.api.documents import router as documents_router  # noqa: E402
from app.api.suggest import router as suggest_router  # noqa: E402

app.include_router(detect_router)
app.include_router(suggest_router)
app.include_router(approvals_router)
app.include_router(documents_router)
app.include_router(ask_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
