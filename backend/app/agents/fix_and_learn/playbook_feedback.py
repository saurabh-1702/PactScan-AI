"""Learning-loop stub (Phase 3).

Full scope ("update the compliance playbook from accepted/rejected outcomes")
is out of scope for this phase — this just proves the feedback data is
actually being captured on every approved edit, per the Phase 3 prompt.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.db.models import PlaybookFeedback


def record_accepted_redline(db: Session, clause_type: str, accepted_text: str) -> PlaybookFeedback:
    row = PlaybookFeedback(clause_type=clause_type, accepted_text=accepted_text)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
