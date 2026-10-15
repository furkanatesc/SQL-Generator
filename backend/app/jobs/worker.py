"""Background job worker process (Sprint 32.4).

    python -m app.jobs.worker              # run until SIGTERM / SIGINT
    python -m app.jobs.worker healthcheck  # exit 0 if the worker loop is alive (Docker HEALTHCHECK)

Claims `pending` jobs from the app database one at a time (`claim_next_job` is atomic, so
several worker processes can share one database), heartbeats while a job runs, and fails
`processing` jobs whose heartbeat is older than `NL2SQL_JOB_STALE_SECONDS` (their worker died).
Use with `NL2SQL_JOB_EXECUTION_MODE=worker` on the API so it only enqueues.
"""
import logging
import os
import signal
import socket
import sys
import tempfile
import threading
import time
import uuid
from typing import Optional

from app.jobs.executor import execute_job
from app.jobs.repository import ABANDONED_MESSAGE, claim_next_job, fail_abandoned_jobs, touch_heartbeat

logger = logging.getLogger(__name__)

DEFAULT_LIVENESS_PATH = os.path.join(tempfile.gettempdir(), "sqlgen_worker_alive")
# The loop touches the file every poll and, during a job, on every heartbeat
# (default stale_seconds / 5 = 60 s); allow a few missed beats.
HEALTHCHECK_MAX_AGE_SECONDS = 180


class JobWorker:
    def __init__(
        self,
        worker_id: Optional[str] = None,
        poll_seconds: float = 1.0,
        stale_seconds: float = 300,
        heartbeat_seconds: Optional[float] = None,
        liveness_path: Optional[str] = None,
    ):
        self.worker_id = worker_id or f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:6]}"
        self.poll_seconds = poll_seconds
        self.stale_seconds = stale_seconds
        self.heartbeat_seconds = heartbeat_seconds or max(1.0, stale_seconds / 5)
        self.liveness_path = liveness_path

    def _mark_alive(self) -> None:
        if not self.liveness_path:
            return
        try:
            with open(self.liveness_path, "a"):
                pass
            os.utime(self.liveness_path, None)
        except OSError:
            logger.warning("cannot update worker liveness file")

    def run_once(self) -> bool:
        """Recover stale jobs, then claim and run at most one job. True if a job ran."""
        self._mark_alive()
        failed = fail_abandoned_jobs(("processing",), older_than_seconds=self.stale_seconds,
                                     message=ABANDONED_MESSAGE)
        if failed:
            logger.warning("failed %d stale job(s) with no worker heartbeat", len(failed))

        job = claim_next_job(self.worker_id)
        if job is None:
            return False

        stop = threading.Event()

        def beat():
            while not stop.wait(self.heartbeat_seconds):
                touch_heartbeat(job["id"], self.worker_id)
                self._mark_alive()

        beater = threading.Thread(target=beat, name=f"heartbeat-{job['id']}", daemon=True)
        beater.start()
        try:
            logger.info("worker %s running job %s", self.worker_id, job["id"])
            execute_job(job["id"])
        except Exception:  # noqa: BLE001 — execute_job records failures; never kill the loop
            logger.exception("job %s crashed the executor", job["id"])
        finally:
            stop.set()
            beater.join(timeout=5)
        return True

    def run_forever(self, stop_event: threading.Event) -> None:
        logger.info("job worker %s started", self.worker_id)
        while not stop_event.is_set():
            try:
                ran = self.run_once()
            except Exception:  # noqa: BLE001 — e.g. database briefly locked
                logger.exception("worker loop error")
                ran = False
            if not ran:
                stop_event.wait(self.poll_seconds)
        logger.info("job worker %s stopped", self.worker_id)


def healthcheck(path: str = DEFAULT_LIVENESS_PATH, max_age_seconds: float = HEALTHCHECK_MAX_AGE_SECONDS) -> bool:
    try:
        return (time.time() - os.path.getmtime(path)) <= max_age_seconds
    except OSError:
        return False


def main(argv=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["healthcheck"]:
        return 0 if healthcheck() else 1

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    from app.database import init_db
    from app.settings import get_settings

    init_db()  # apply migrations (safe alongside the API: runner takes the write lock)
    settings = get_settings()
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    JobWorker(
        poll_seconds=settings.job_worker_poll_seconds,
        stale_seconds=settings.job_stale_seconds,
        liveness_path=DEFAULT_LIVENESS_PATH,
    ).run_forever(stop)
    return 0


if __name__ == "__main__":
    sys.exit(main())
