"""API-startup job recovery (Sprint 32.4)."""
from typing import List

from app.jobs.repository import RESTART_MESSAGE, fail_abandoned_jobs
from app.settings import get_settings


def recover_jobs_on_api_startup() -> List[str]:
    """Inline mode: jobs left `pending`/`processing` by a previous API process can never
    resume (their BackgroundTask died with it), so they are failed. Worker mode: the worker
    owns recovery (heartbeat based), so nothing is touched here."""
    if get_settings().job_execution_mode != "inline":
        return []
    return fail_abandoned_jobs(("pending", "processing"), message=RESTART_MESSAGE)
