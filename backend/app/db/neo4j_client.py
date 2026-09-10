"""Neo4j driver connection helper.

Phase 0: connection helper only — no graph schema or queries yet.
Real graph modeling begins in Phase 1.
"""

from __future__ import annotations

from neo4j import GraphDatabase, Driver

from app.config import settings

_driver: Driver | None = None


def get_driver() -> Driver:
    """Return a lazily-initialised, process-wide Neo4j driver."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
    return _driver


def verify_connectivity() -> None:
    """Raise if Neo4j is unreachable. Used by the FastAPI startup check."""
    get_driver().verify_connectivity()


def close_driver() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None
