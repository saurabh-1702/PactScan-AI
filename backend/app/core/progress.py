"""Real, stage-based progress for long-running work (frontend redesign).

Detect (and Ask's attach, which runs Detect) takes long enough that a bare
spinner is dishonest and a fake percentage is worse. The pipeline reports the
stage it is *actually* in; the UI polls and shows real steps — never a
percentage — and a global "N processes running" indicator reads the same store.

Same two-implementation pattern as app.core.rate_limit / GraphStore: Redis for
real runs, in-memory for the mocked suite. Progress is strictly best-effort:
if Redis is unreachable every call degrades to a no-op with a warning, and the
work itself is never affected.
"""

from __future__ import annotations

import abc
import json
import logging
import time
from typing import Any

import redis

from app.config import settings

logger = logging.getLogger("pactscan.progress")

JOB_TTL_SECONDS = 3600
# A "running" job not touched for this long is treated as dead (e.g. the server
# restarted mid-run) so it can't sit in the indicator forever.
STALE_AFTER_SECONDS = 600

# (key, label) — order is the order the pipeline reports them.
DETECT_STAGES: list[tuple[str, str]] = [
    ("parse", "Reading the document"),
    ("extract", "Identifying clauses"),
    ("graph", "Building the contract graph"),
    ("check", "Checking against playbook and regulations"),
    ("save", "Saving the version and sending notifications"),
]


def _new_job(job_id: str, user_id: str, tenant_id: str, label: str, stages: list[tuple[str, str]]) -> dict:
    now = time.time()
    return {
        "job_id": job_id,
        "user_id": user_id,
        "tenant_id": tenant_id,
        "label": label,
        "state": "running",
        "error": None,
        "stages": [{"key": k, "label": lbl, "status": "pending"} for k, lbl in stages],
        "started_at": now,
        "updated_at": now,
    }


def _advance(job: dict, stage_key: str) -> None:
    """Marks every stage before ``stage_key`` done and ``stage_key`` active."""
    reached = False
    for s in job["stages"]:
        if s["key"] == stage_key:
            s["status"] = "active"
            reached = True
        elif not reached:
            s["status"] = "done"
    job["updated_at"] = time.time()


def _finish(job: dict) -> None:
    for s in job["stages"]:
        s["status"] = "done"
    job["state"] = "done"
    job["updated_at"] = time.time()


def _fail(job: dict, message: str) -> None:
    for s in job["stages"]:
        if s["status"] == "active":
            s["status"] = "failed"
    job["state"] = "failed"
    job["error"] = message
    job["updated_at"] = time.time()


def public_view(job: dict) -> dict:
    """The job without the user/tenant ids — what the API returns."""
    return {k: v for k, v in job.items() if k not in ("user_id", "tenant_id")}


class ProgressTracker(abc.ABC):
    @abc.abstractmethod
    def _load(self, job_id: str) -> dict | None: ...

    @abc.abstractmethod
    def _save(self, job: dict) -> None: ...

    @abc.abstractmethod
    def _user_job_ids(self, user_id: str) -> list[str]: ...

    def start(
        self, job_id: str, user_id: str, tenant_id: str, label: str, stages: list[tuple[str, str]]
    ) -> bool:
        """False if ``job_id`` already belongs to someone else (so one user
        can't overwrite another's job by guessing an id)."""
        existing = self._load(job_id)
        if existing is not None and existing["user_id"] != user_id:
            return False
        self._save(_new_job(job_id, user_id, tenant_id, label, stages))
        return True

    def advance(self, job_id: str, stage_key: str) -> None:
        job = self._load(job_id)
        if job is not None:
            _advance(job, stage_key)
            self._save(job)

    def finish(self, job_id: str) -> None:
        job = self._load(job_id)
        if job is not None:
            _finish(job)
            self._save(job)

    def fail(self, job_id: str, message: str) -> None:
        job = self._load(job_id)
        if job is not None:
            _fail(job, message)
            self._save(job)

    def get(self, job_id: str, user_id: str) -> dict | None:
        job = self._load(job_id)
        if job is None or job["user_id"] != user_id:
            return None
        return job

    def list_active(self, user_id: str) -> list[dict]:
        now = time.time()
        out = []
        for job_id in self._user_job_ids(user_id):
            job = self._load(job_id)
            if (
                job is not None
                and job["state"] == "running"
                and now - job["updated_at"] < STALE_AFTER_SECONDS
            ):
                out.append(job)
        out.sort(key=lambda j: j["started_at"])
        return out


class InMemoryProgressTracker(ProgressTracker):
    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}

    def _load(self, job_id: str) -> dict | None:
        job = self._jobs.get(job_id)
        return json.loads(json.dumps(job)) if job is not None else None

    def _save(self, job: dict) -> None:
        self._jobs[job["job_id"]] = json.loads(json.dumps(job))

    def _user_job_ids(self, user_id: str) -> list[str]:
        return [jid for jid, j in self._jobs.items() if j["user_id"] == user_id]


class RedisProgressTracker(ProgressTracker):
    def __init__(self, client: "redis.Redis | None" = None) -> None:
        self._client = client or redis.Redis.from_url(settings.redis_url)

    @staticmethod
    def _key(job_id: str) -> str:
        return f"progress:job:{job_id}"

    @staticmethod
    def _user_key(user_id: str) -> str:
        return f"progress:user:{user_id}"

    def _load(self, job_id: str) -> dict | None:
        try:
            raw = self._client.get(self._key(job_id))
            return json.loads(raw) if raw else None
        except redis.RedisError:
            logger.warning("Redis unreachable — progress unavailable", exc_info=True)
            return None

    def _save(self, job: dict) -> None:
        try:
            pipe = self._client.pipeline()
            pipe.set(self._key(job["job_id"]), json.dumps(job), ex=JOB_TTL_SECONDS)
            pipe.sadd(self._user_key(job["user_id"]), job["job_id"])
            pipe.expire(self._user_key(job["user_id"]), JOB_TTL_SECONDS)
            pipe.execute()
        except redis.RedisError:
            logger.warning("Redis unreachable — progress not recorded", exc_info=True)

    def _user_job_ids(self, user_id: str) -> list[str]:
        try:
            return [m.decode() if isinstance(m, bytes) else m for m in self._client.smembers(self._user_key(user_id))]
        except redis.RedisError:
            logger.warning("Redis unreachable — progress unavailable", exc_info=True)
            return []


_default_tracker: ProgressTracker | None = None


def get_progress_tracker() -> ProgressTracker:
    global _default_tracker
    if _default_tracker is None:
        _default_tracker = RedisProgressTracker()
    return _default_tracker


class JobProgress:
    """What a pipeline holds: reports stages for one job, and does nothing at
    all when there is no job (the default) — so callers never need ``if``s."""

    def __init__(self, tracker: ProgressTracker | None = None, job_id: str | None = None) -> None:
        self._tracker = tracker
        self._job_id = job_id

    @classmethod
    def begin(
        cls,
        job_id: str | None,
        user_id: str | None,
        tenant_id: str,
        label: str,
        stages: list[tuple[str, str]] = DETECT_STAGES,
    ) -> "JobProgress":
        if not job_id or not user_id:
            return cls()
        tracker = get_progress_tracker()
        try:
            if not tracker.start(job_id, user_id, tenant_id, label, stages):
                return cls()
        except Exception:  # noqa: BLE001 - progress must never break the work itself
            logger.warning("Could not start progress tracking", exc_info=True)
            return cls()
        return cls(tracker, job_id)

    def _safe(self, fn: Any, *args: Any) -> None:
        if self._tracker is None or self._job_id is None:
            return
        try:
            fn(self._job_id, *args)
        except Exception:  # noqa: BLE001
            logger.warning("Progress update failed", exc_info=True)

    def advance(self, stage_key: str) -> None:
        self._safe(self._tracker.advance if self._tracker else None, stage_key)

    def finish(self) -> None:
        self._safe(self._tracker.finish if self._tracker else None)

    def fail(self, message: str) -> None:
        self._safe(self._tracker.fail if self._tracker else None, message)
