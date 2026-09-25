"""Wipe everything a user creates while using PactScan — WITHOUT stopping the
backend, the frontend or Docker.

Removes:  contracts, clauses and findings (Neo4j), simulated regulation updates,
          drafts, approvals, document versions (and the stored files), restore
          requests, notifications, Ask conversations, the audit log, the playbook
          feedback, and the Redis rate-limit / progress state.
Keeps:    user accounts and tenants (so you stay able to log in), the seeded
          playbook rules, and the baseline DPDP / GDPR regulation clauses.

Run from the backend folder:

    .\\venv\\Scripts\\python.exe scripts\\reset_app_data.py --yes

Without --yes (or with --dry-run) it only reports what it WOULD delete.
Signed-in browsers keep working; just refresh the page.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

import redis  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.config import settings  # noqa: E402
from app.db import neo4j_client  # noqa: E402
from app.db.postgres_client import engine  # noqa: E402

# Postgres tables holding what users created. `users` and `tenants` are NOT here.
PG_TABLES = [
    "approvals",
    "redline_suggestions",
    "document_versions",
    "restore_requests",
    "notifications",
    "chat_messages",
    "chat_sessions",
    "playbook_feedback",
    "audit_log",
]

AMENDMENT_PREFIX = "Amendment effective"


def _count_pg() -> dict[str, int]:
    with engine.connect() as conn:
        return {t: conn.execute(text(f"SELECT count(*) FROM {t}")).scalar_one() for t in PG_TABLES}


def _count_neo() -> dict[str, int]:
    driver = neo4j_client.get_driver()
    with driver.session() as s:
        return {
            "contracts": s.run("MATCH (n:Contract) RETURN count(n) AS c").single()["c"],
            "clauses": s.run("MATCH (n:Clause) RETURN count(n) AS c").single()["c"],
            "findings": s.run("MATCH (n:Finding) RETURN count(n) AS c").single()["c"],
            "simulated regulation updates": s.run(
                "MATCH (r:RegulationClause) WHERE r.section STARTS WITH $p RETURN count(r) AS c",
                p=AMENDMENT_PREFIX,
            ).single()["c"],
        }


def _stored_files() -> list[Path]:
    root = BACKEND_DIR / "storage" / "documents"
    return [p for p in root.rglob("*") if p.is_file()] if root.exists() else []


def report() -> None:
    print("Postgres rows:")
    for table, n in _count_pg().items():
        print(f"  {table:<22} {n}")
    print("Neo4j:")
    for label, n in _count_neo().items():
        print(f"  {label:<28} {n}")
    print(f"Stored document files:   {len(_stored_files())}")


def wipe() -> None:
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {', '.join(PG_TABLES)} RESTART IDENTITY CASCADE"))
    print("Postgres: cleared.")

    driver = neo4j_client.get_driver()
    with driver.session() as s:
        # in batches so a large graph can't exhaust transaction memory
        while s.run(
            "MATCH (n) WHERE n:Contract OR n:Clause OR n:Finding "
            "WITH n LIMIT 5000 DETACH DELETE n RETURN count(*) AS c"
        ).single()["c"]:
            pass
        s.run(
            "MATCH (r:RegulationClause) WHERE r.section STARTS WITH $p DETACH DELETE r",
            p=AMENDMENT_PREFIX,
        )
    print("Neo4j: contracts, clauses, findings and simulated regulation updates cleared.")

    try:
        redis.Redis.from_url(settings.redis_url).flushall()
        print("Redis: cleared (rate limits and job progress reset).")
    except redis.RedisError as exc:
        print(f"Redis: skipped ({exc})")

    root = BACKEND_DIR / "storage" / "documents"
    if root.exists():
        for child in root.iterdir():
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    print("Stored document files: cleared.")


def main() -> None:
    args = set(sys.argv[1:])
    if "--yes" not in args or "--dry-run" in args:
        print("DRY RUN — nothing is deleted. Add --yes to actually wipe.\n")
        report()
        return
    report()
    print("\nWiping…")
    wipe()
    print("\nDone. Refresh the browser. Accounts, playbook rules and baseline regulations are untouched.")


if __name__ == "__main__":
    main()
