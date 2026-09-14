"""Restore abuse-flagging (Phase 6).

Doesn't block anything — a genuinely bad approved edit might legitimately
need reverting more than once. It just surfaces a warning so a reviewer
notices a pattern (e.g. someone repeatedly requesting reverts to dodge
review) rather than deciding each request in isolation.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import AuditLog, RestoreRequest


def check_and_flag_restore_abuse(db: Session, contract_id: str, new_request_id: str) -> bool:
    """Counts approved restore_requests for this contract within the
    flagging window. If at or past the threshold, marks ``new_request_id``
    abuse_flagged and logs a restore_pattern_flagged audit entry. Returns
    whether it flagged."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=settings.restore_abuse_window_days)
    approved_count = (
        db.query(RestoreRequest)
        .filter(
            RestoreRequest.contract_id == contract_id,
            RestoreRequest.status == "approved",
            RestoreRequest.decided_at >= cutoff,
        )
        .count()
    )
    if approved_count < settings.restore_abuse_threshold:
        return False

    request = db.get(RestoreRequest, new_request_id)
    if request is not None:
        request.abuse_flagged = True
    db.add(
        AuditLog(
            event_type="restore_pattern_flagged",
            entity_id=new_request_id,
            details=json.dumps(
                {
                    "contract_id": contract_id,
                    "approved_restores_in_window": approved_count,
                    "window_days": settings.restore_abuse_window_days,
                }
            ),
        )
    )
    db.commit()
    return True
