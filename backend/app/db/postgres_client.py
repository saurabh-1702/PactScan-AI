"""SQLAlchemy engine + session setup.

Phase 0: engine/session factory only — no ORM models or migrations yet.
Application tables are introduced in later phases.
"""

from __future__ import annotations

from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import settings

engine = create_engine(settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)
Base = declarative_base()


def get_db():
    """FastAPI dependency that yields a session and always closes it."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def verify_connectivity() -> None:
    """Raise if Postgres is unreachable. Used by the FastAPI startup check."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
