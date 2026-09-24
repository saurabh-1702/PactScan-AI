"""Notification-firing hook (Phase 5).

Called once per new Finding, right after Detect writes it to the graph (see
app/agents/detect/pipeline.py::ingest_and_detect). Always inserts an in-app
`notifications` row; a HIGH-severity finding additionally makes a best-effort
attempt to email every reviewer/admin in the tenant via Resend.

Email is optional and degrades gracefully: with no RESEND_API_KEY configured,
or if the Resend call itself fails, the in-app notification still exists —
email is a bonus channel, never a dependency for the notification to "count".
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from app.config import settings
from app.db.models import Notification, RedlineSuggestion, RestoreRequest, User
from app.models.clause import Finding

logger = logging.getLogger("pactscan.notifications")


def notify_new_findings(
    db: Session,
    tenant_id: str,
    contract_filename: str,
    findings: list[Finding],
    contract_owner_user_id: str | None = None,
) -> None:
    if not findings:
        return

    high_severity: list[tuple[Notification, Finding]] = []
    for finding in findings:
        message = (
            f"{finding.severity.value} finding in {contract_filename} "
            f"(page {finding.page_number}): {finding.rule_or_regulation_violated}"
        )
        row = Notification(
            tenant_id=tenant_id,
            contract_owner_user_id=contract_owner_user_id,
            finding_id=finding.finding_id,
            severity=finding.severity.value,
            message=message,
        )
        db.add(row)
        if finding.severity.value == "HIGH":
            high_severity.append((row, finding))
    db.commit()

    if high_severity and settings.resend_api_key:
        _send_high_severity_emails(db, tenant_id, contract_filename, high_severity)


def notify_approval_decision(
    db: Session,
    suggestion: RedlineSuggestion,
    decision: str,
    reviewer_note: str | None,
    edited_text: str | None,
    document_version_id: str | None,
    decided_by_user_id: str | None,
) -> None:
    """Closes the loop back to whoever drafted this suggestion (Suggest, or
    Ask's edit-instruction handoff) once a reviewer/admin decides it.
    Addressed to that one user (Notification.recipient_user_id), not
    broadcast — unlike notify_new_findings above.

    Skipped entirely when the draft has no traceable requester (created
    before this column existed, or via a direct pipeline call with no
    authenticated caller), or when the requester is the same person who just
    decided it — no point notifying yourself about your own action.
    """
    if not suggestion.requested_by_user_id:
        return
    if suggestion.requested_by_user_id == decided_by_user_id:
        return

    if decision == "rejected":
        reason = reviewer_note or "No reason was given."
        message = (
            f"Your suggested fix for clause {suggestion.clause_id} was rejected. "
            f"Reviewer's note: {reason}"
        )
        version_id = None
    else:
        was_edited = bool(edited_text) and edited_text != suggestion.proposed_text
        if was_edited:
            message = (
                f"Your suggested fix for clause {suggestion.clause_id} was approved, but a "
                "reviewer wrote their own edit instead of using your exact wording. A new "
                "document version is available."
            )
        else:
            message = (
                f"Your suggested fix for clause {suggestion.clause_id} was approved and "
                "applied. A new document version is available."
            )
        version_id = document_version_id

    db.add(
        Notification(
            kind="approval_decided",
            tenant_id=suggestion.tenant_id,
            recipient_user_id=suggestion.requested_by_user_id,
            finding_id=suggestion.finding_id,
            severity=None,
            message=message,
            document_version_id=version_id,
        )
    )
    db.commit()


def notify_restore_decision(
    db: Session,
    request: RestoreRequest,
    decision: str,
    reviewer_note: str | None,
    new_version_id: str | None,
    decided_by_user_id: str | None,
) -> None:
    """Closes the loop back to whoever requested a restore, mirroring
    ``notify_approval_decision`` above. Skipped if the requester is the
    person who decided it."""
    if request.requested_by_user_id == decided_by_user_id:
        return

    if decision == "rejected":
        reason = reviewer_note or "No reason was given."
        message = f"Your restore request for contract {request.contract_id} was rejected. Reviewer's note: {reason}"
        version_id = None
    else:
        message = (
            f"Your restore request for contract {request.contract_id} was approved. "
            "A new document version is available."
        )
        version_id = new_version_id

    db.add(
        Notification(
            kind="approval_decided",
            tenant_id=request.tenant_id,
            recipient_user_id=request.requested_by_user_id,
            finding_id=None,
            severity=None,
            message=message,
            document_version_id=version_id,
        )
    )
    db.commit()


def _send_high_severity_emails(
    db: Session,
    tenant_id: str,
    contract_filename: str,
    high_severity: list[tuple[Notification, "Finding"]],
) -> None:
    recipients = (
        db.query(User)
        .filter(User.tenant_id == tenant_id, User.role.in_(["reviewer", "admin"]))
        .all()
    )
    if not recipients:
        return

    import resend

    resend.api_key = settings.resend_api_key
    lines = [
        f"- {finding.rule_or_regulation_violated} (page {finding.page_number})"
        for _, finding in high_severity
    ]
    body = (
        f"{len(high_severity)} HIGH severity finding(s) in {contract_filename}:\n\n"
        + "\n".join(lines)
    )
    # Each recipient is sent independently — one bad/unverified address (e.g.
    # a fake seeded demo account, under Resend's sandbox restriction) must
    # never prevent the rest of the tenant's reviewers/admins from being
    # notified. A single shared try/except around the whole loop would abort
    # on the first failure and silently skip everyone after it.
    for user in recipients:
        try:
            resend.Emails.send(
                {
                    "from": settings.notification_email_from,
                    "to": [user.email],
                    "subject": f"PactScan AI: HIGH severity finding(s) in {contract_filename}",
                    "text": body,
                }
            )
        except Exception:  # noqa: BLE001 - email is a bonus channel, never fatal
            logger.warning(
                "HIGH-severity email notification failed for %s (in-app row already saved)",
                user.email,
                exc_info=True,
            )
