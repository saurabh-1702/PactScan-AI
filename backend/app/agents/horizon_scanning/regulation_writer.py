"""Horizon-Scanning (Phase 6) — writing a simulated regulation update.

Honesty note (also surfaced in the frontend, per the phase's own
requirement): real 24/7 monitoring against government regulatory feeds is
out of scope. This is the mechanism a real scheduler would call — triggered
manually here via an admin-only endpoint instead of on a timer.
"""

from __future__ import annotations

from app.agents.detect.graph_store import GraphStore


def add_regulation_update(
    store: GraphStore, regulation_name: str, new_clause_text: str, effective_date: str
) -> dict:
    """Inserts a new RegulationClause representing an amendment/new rule
    under an existing regulation (DPDP or GDPR). Returns the created clause
    dict: {id, regulation_name, section, text, effective_date}."""
    return store.add_regulation_update(regulation_name, new_clause_text, effective_date)
