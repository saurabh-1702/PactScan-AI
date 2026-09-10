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


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
