"""Tiny, idempotent schema upgrades applied at startup.

There is no migration framework yet (``Base.metadata.create_all`` only creates
tables that are missing, never new columns on existing ones), so a column added
after a table first existed would break every existing dev/prod database until
someone reset it by hand. Each upgrade here adds one nullable column if — and
only if — it is missing, so upgrading is just "restart the backend".
"""

from __future__ import annotations

import logging

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

logger = logging.getLogger("pactscan.db.schema_upgrades")

# (table, column, SQL type) — every entry must be nullable.
COLUMN_UPGRADES: list[tuple[str, str, str]] = [
    # Snapshot of the clause's wording when a draft was made, so a draft's
    # history stays readable after a re-scan replaces the contract's clauses.
    ("redline_suggestions", "original_clause_text", "TEXT"),
]


def apply_schema_upgrades(engine: Engine) -> list[str]:
    """Returns the ``table.column`` names that were added (empty if up to date)."""
    added: list[str] = []
    inspector = inspect(engine)
    for table, column, sql_type in COLUMN_UPGRADES:
        if table not in inspector.get_table_names():
            continue  # create_all will build it with the column already in place
        if column in {c["name"] for c in inspector.get_columns(table)}:
            continue
        with engine.begin() as conn:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {sql_type}"))
        logger.info("Schema upgrade: added %s.%s", table, column)
        added.append(f"{table}.{column}")
    return added
