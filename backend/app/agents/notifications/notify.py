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
from app.db.models import Notification, User
from app.models.clause import Finding

logger = logging.getLogger("pactscan.notifications")


def notify_new_findings(
    db: Session, tenant_id: str, contract_filename: str, findings: list[Finding]
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

    try:
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
        for user in recipients:
            resend.Emails.send(
                {
                    "from": settings.notification_email_from,
                    "to": [user.email],
                    "subject": f"PactScan AI: HIGH severity finding(s) in {contract_filename}",
                    "text": body,
                }
            )
    except Exception:  # noqa: BLE001 - email is a bonus channel, never fatal
        logger.warning("HIGH-severity email notification failed (in-app rows already saved)", exc_info=True)
