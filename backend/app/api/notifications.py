"""Notification API (Phase 5).

GET  /api/notifications?unread_only=true  -> list this tenant's notifications
POST /api/notifications/{id}/mark-read    -> mark one as read
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.api.deps import CurrentUser, get_current_user
from app.db.models import Notification
from app.db.postgres_client import get_db
from app.models.notification import NotificationOut

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


@router.get("", response_model=list[NotificationOut])
def list_notifications(
    unread_only: bool = Query(default=False),
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> list[NotificationOut]:
    if current_user.role == "end_user":
        # own targeted notifications + tenant broadcasts, but only broadcasts
        # about contracts this user uploaded
        visible = or_(
            Notification.recipient_user_id == current_user.user_id,
            and_(
                Notification.recipient_user_id.is_(None),
                Notification.contract_owner_user_id == current_user.user_id,
            ),
        )
    else:
        visible = or_(
            Notification.recipient_user_id.is_(None),
            Notification.recipient_user_id == current_user.user_id,
        )
    q = db.query(Notification).filter(Notification.tenant_id == current_user.tenant_id, visible)
    if unread_only:
        q = q.filter(Notification.is_read.is_(False))
    rows = q.order_by(Notification.created_at.desc()).all()
    return [NotificationOut.model_validate(r, from_attributes=True) for r in rows]


@router.post("/{notification_id}/mark-read", response_model=NotificationOut)
def mark_read(
    notification_id: str,
    db: Session = Depends(get_db),
    current_user: CurrentUser = Depends(get_current_user),
) -> NotificationOut:
    row = db.get(Notification, notification_id)
    # A targeted notification (recipient_user_id set) may only be marked read
    # by its recipient; a broadcast one (recipient_user_id None) is shared
    # tenant-wide, matching how the whole notification feed already works for
    # those — there's no per-user read state for a shared row.
    if (
        row is None
        or row.tenant_id != current_user.tenant_id
        or (row.recipient_user_id is not None and row.recipient_user_id != current_user.user_id)
    ):
        raise HTTPException(404, f"notification {notification_id!r} not found")
    row.is_read = True
    db.commit()
    db.refresh(row)
    return NotificationOut.model_validate(row, from_attributes=True)
