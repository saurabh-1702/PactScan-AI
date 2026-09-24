"""Real-progress polling for long-running work.

GET /api/progress/active        -> the caller's own running jobs (feeds the
                                    global "N processes running" indicator)
GET /api/progress/{job_id}      -> one of the caller's own jobs, stage by stage

Read-only, and scoped to the caller: a job id belonging to someone else is a
404, not a 403, so its existence isn't revealed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import CurrentUser, get_current_user
from app.core.progress import ProgressTracker, get_progress_tracker, public_view

router = APIRouter(prefix="/api/progress", tags=["progress"])


@router.get("/active")
def active_jobs(
    current_user: CurrentUser = Depends(get_current_user),
    tracker: ProgressTracker = Depends(get_progress_tracker),
) -> list[dict]:
    return [public_view(j) for j in tracker.list_active(current_user.user_id)]


@router.get("/{job_id}")
def job_progress(
    job_id: str,
    current_user: CurrentUser = Depends(get_current_user),
    tracker: ProgressTracker = Depends(get_progress_tracker),
) -> dict:
    job = tracker.get(job_id, current_user.user_id)
    if job is None:
        raise HTTPException(404, f"job {job_id!r} not found")
    return public_view(job)
