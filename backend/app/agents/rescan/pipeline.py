"""Re-scan a contract's CURRENT version.

Findings are created from the original upload. An approved edit or a restore
changes the document but never the findings, so after either the two can
disagree. A re-scan reads the latest version *as the parties would sign it*
(the clean, changes-accepted copy), refreshes the contract's clauses and
findings, and re-checks it against every regulation update recorded since —
so "fix, then a new regulation, then re-fix, then verify" is possible.

Safety, because this replaces a contract's clauses (each gets a new id):
  * it is refused while anything is pending against the contract — a pending
    approval or restore, or a draft that has not been submitted yet — because
    those point at the old clauses;
  * the new clauses are extracted BEFORE anything is deleted, so an unreadable
    document or a failed parse changes nothing;
  * drafts keep a snapshot of the wording they were written against, so history
    stays readable afterwards;
  * no notifications or emails are sent — the findings are not new news;
  * every run is recorded in the audit log (started / completed / failed).
"""

from __future__ import annotations

import json
import logging
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy.orm import Session

from app.agents.detect import graph_writer, ingest
from app.agents.detect.detect_agent import run_detect
from app.agents.detect.graph_store import GraphStore
from app.agents.fix_and_learn.clean_copy import make_clean_docx
from app.agents.horizon_scanning.rediff import rediff_regulation_update
from app.core.progress import JobProgress
from app.db.models import Approval, AuditLog, DocumentVersion, RedlineSuggestion, RestoreRequest

logger = logging.getLogger("pactscan.rescan")

RESCAN_STAGES: list[tuple[str, str]] = [
    ("parse", "Reading the current version"),
    ("extract", "Identifying clauses"),
    ("graph", "Rebuilding the contract graph"),
    ("check", "Checking against the playbook, regulations and updates"),
    ("save", "Saving the results"),
]

AMENDMENT_PREFIX = "Amendment effective"
# A rescan that started this long ago and never finished is treated as dead.
RUNNING_WINDOW = timedelta(minutes=15)

_STARTED = "contract_rescan_started"
_COMPLETED = "contract_rescan_completed"
_FAILED = "contract_rescan_failed"
_RESTORED = "document_restored"


class RescanBlockedError(Exception):
    """A user-facing 409: the re-scan can't start right now."""


class RescanInputError(Exception):
    """A user-facing 422: there's nothing usable to re-scan."""


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def rescan_blockers(db: Session, contract_id: str, tenant_id: str) -> dict[str, int]:
    """What is still pending against this contract (each would point at clauses
    a re-scan replaces)."""
    pending_approvals = (
        db.query(Approval)
        .join(RedlineSuggestion, Approval.redline_suggestion_id == RedlineSuggestion.id)
        .filter(
            RedlineSuggestion.tenant_id == tenant_id,
            RedlineSuggestion.contract_id == contract_id,
            Approval.status == "pending",
        )
        .count()
    )
    pending_restores = (
        db.query(RestoreRequest)
        .filter(
            RestoreRequest.tenant_id == tenant_id,
            RestoreRequest.contract_id == contract_id,
            RestoreRequest.status == "pending",
        )
        .count()
    )
    submitted_ids = db.query(Approval.redline_suggestion_id)
    unsubmitted_drafts = (
        db.query(RedlineSuggestion)
        .filter(
            RedlineSuggestion.tenant_id == tenant_id,
            RedlineSuggestion.contract_id == contract_id,
            ~RedlineSuggestion.id.in_(submitted_ids),
        )
        .count()
    )
    return {
        "pending_approvals": pending_approvals,
        "pending_restores": pending_restores,
        "unsubmitted_drafts": unsubmitted_drafts,
    }


def _blocker_message(b: dict[str, int]) -> str:
    parts = []
    if b["pending_approvals"]:
        parts.append(f"{b['pending_approvals']} draft(s) waiting for a reviewer")
    if b["pending_restores"]:
        parts.append(f"{b['pending_restores']} restore request(s) waiting for a decision")
    if b["unsubmitted_drafts"]:
        parts.append(f"{b['unsubmitted_drafts']} draft(s) not yet submitted")
    return (
        "A re-scan replaces this contract's clauses, so it can't run while there are "
        + ", ".join(parts)
        + ". Decide, submit or delete them first."
    )


def scan_info(db: Session, contract_id: str, tenant_id: str) -> dict:
    """Which version the findings describe, and whether that is still the
    current wording. A restored copy has the same wording as the version it was
    copied from, so restoring to the scanned version is NOT stale."""
    versions = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.tenant_id == tenant_id, DocumentVersion.contract_id == contract_id)
        .order_by(DocumentVersion.version_number)
        .all()
    )
    latest_version = versions[-1].version_number if versions else 1

    events = (
        db.query(AuditLog)
        .filter(
            AuditLog.entity_id == contract_id,
            AuditLog.event_type.in_([_STARTED, _COMPLETED, _FAILED, _RESTORED]),
        )
        .order_by(AuditLog.created_at)
        .all()
    )

    # version -> the version whose wording it copies (follows restore chains)
    copies: dict[int, int] = {}
    scanned_version = 1
    last_completed_at: datetime | None = None
    last_started: AuditLog | None = None
    last_outcome_after_start: str | None = None
    for e in events:
        details = json.loads(e.details or "{}")
        if e.event_type == _RESTORED:
            copies[int(details["new_version"])] = int(details["target_version_number"])
        elif e.event_type == _STARTED:
            last_started, last_outcome_after_start = e, None
        elif e.event_type == _COMPLETED:
            scanned_version = int(details["version_number"])
            last_completed_at = e.created_at
            last_outcome_after_start = "completed"
        elif e.event_type == _FAILED:
            # a failure before anything was replaced left the contract as it was
            last_outcome_after_start = "failed" if details.get("changed", True) else "unchanged"

    def wording_of(v: int) -> int:
        seen = set()
        while v in copies and v not in seen:
            seen.add(v)
            v = copies[v]
        return v

    now = datetime.now(timezone.utc)
    started_recently = (
        last_started is not None and now - _aware(last_started.created_at) < RUNNING_WINDOW
    )
    running = last_started is not None and last_outcome_after_start is None and started_recently
    # started but never finished (and not merely still running) = a failed run
    incomplete = last_started is not None and (
        last_outcome_after_start == "failed"
        or (last_outcome_after_start is None and not started_recently)
    )
    if last_outcome_after_start == "unchanged":
        running = incomplete = False

    blockers = rescan_blockers(db, contract_id, tenant_id)
    return {
        "latest_version": latest_version,
        "scanned_version": scanned_version,
        "stale": wording_of(latest_version) != wording_of(scanned_version),
        "running": running,
        "incomplete": incomplete,
        "last_rescan_at": last_completed_at,
        "blockers": blockers,
        "can_rescan": not running and not any(blockers.values()) and bool(versions),
    }


def _audit(db: Session, event: str, contract_id: str, **details) -> None:
    db.add(AuditLog(event_type=event, entity_id=contract_id, details=json.dumps(details)))
    db.commit()


async def rescan_contract(
    store: GraphStore,
    db: Session,
    contract_id: str,
    tenant_id: str,
    user_id: str,
    progress: JobProgress | None = None,
) -> dict:
    progress = progress or JobProgress()
    info = scan_info(db, contract_id, tenant_id)
    if info["running"]:
        raise RescanBlockedError("A re-scan of this contract is already running.")
    if any(info["blockers"].values()):
        raise RescanBlockedError(_blocker_message(info["blockers"]))

    latest = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.tenant_id == tenant_id, DocumentVersion.contract_id == contract_id)
        .order_by(DocumentVersion.version_number.desc())
        .first()
    )
    if latest is None or not Path(latest.file_path).exists():
        raise RescanInputError("This contract has no stored document version to re-scan.")

    contract = next(
        (c for c in store.list_contracts(tenant_id=tenant_id) if c["contract_id"] == contract_id),
        None,
    )
    if contract is None:
        raise RescanInputError(f"Contract {contract_id!r} not found.")

    _audit(db, _STARTED, contract_id, version_number=latest.version_number, by=user_id)
    changed = False  # flips to True the moment the old analysis is replaced
    try:
        progress.advance("parse")
        clean = make_clean_docx(Path(latest.file_path).read_bytes(), strip_preamble=True)
        with tempfile.TemporaryDirectory(prefix="pactscan_rescan_") as tmp:
            path = Path(tmp) / f"{Path(contract['filename']).stem}.docx"
            path.write_bytes(clean)
            parsed = ingest.parse_document(path)
            progress.advance("extract")
            clauses = await ingest.extract_clauses(parsed, contract_id)
        if not clauses:
            raise RescanInputError("No clauses could be read from the current version.")

        # Everything above can fail without changing anything. From here on the
        # old analysis is replaced.
        findings_before = len(store.get_findings(contract_id, tenant_id=tenant_id))
        progress.advance("graph")
        changed = True
        store.reset_contract_analysis(contract_id, tenant_id=tenant_id)
        await graph_writer.write_contract_graph(
            store,
            contract_id,
            contract["filename"],
            clauses,
            tenant_id=tenant_id,
            uploaded_by_user_id=contract.get("uploaded_by_user_id"),
        )

        progress.advance("check")
        await run_detect(store, contract_id, tenant_id=tenant_id)
        # run_detect only knows the seeded regulations; also re-check every
        # regulation update recorded since (quietly — these aren't new news).
        for reg in store.get_regulation_clauses():
            if str(reg.get("section") or "").startswith(AMENDMENT_PREFIX):
                await rediff_regulation_update(
                    store, db, reg, tenant_id=tenant_id, only_contract_id=contract_id, notify=False
                )

        progress.advance("save")
        findings_after = len(store.get_findings(contract_id, tenant_id=tenant_id))
        _audit(
            db,
            _COMPLETED,
            contract_id,
            version_number=latest.version_number,
            findings_before=findings_before,
            findings_after=findings_after,
            by=user_id,
        )
    except Exception as exc:
        db.rollback()
        _audit(db, _FAILED, contract_id, error=str(exc)[:500], changed=changed, by=user_id)
        progress.fail(str(exc) or exc.__class__.__name__)
        raise

    progress.finish()
    logger.info(
        "Re-scanned %s at v%d: %d -> %d findings",
        contract_id,
        latest.version_number,
        findings_before,
        findings_after,
    )
    return {
        "contract_id": contract_id,
        "scanned_version": latest.version_number,
        "findings_before": findings_before,
        "findings_after": findings_after,
    }
