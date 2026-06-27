import asyncio
import logging
import os
import socket
import sys
from pathlib import Path
from uuid import UUID

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database import AsyncSessionLocal  # noqa: E402
from app.models import NotificationJob  # noqa: E402
from app.notifications import send_telegram_message  # noqa: E402
from app.schema_migrations import ensure_sqlite_schema  # noqa: E402
from app.services import push_service  # noqa: E402
from app.services.notification_queue import (  # noqa: E402
    JOB_TYPE_TELEGRAM,
    JOB_TYPE_WEB_PUSH,
    claim_pending_jobs,
    decode_job_payload,
    mark_job_failed,
    mark_job_sent,
    recover_stale_processing_jobs,
)


load_dotenv(PROJECT_ROOT / ".env", override=False)

logging.basicConfig(
    level=os.getenv("NOTIFICATION_WORKER_LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [notification-worker] %(message)s",
)
logger = logging.getLogger(__name__)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid %s=%r; using %s", name, raw, default)
        return default


def _positive_env_int(name: str, default: int) -> int:
    value = _env_int(name, default)
    if value < 1:
        logger.warning("Invalid %s=%s; using %s", name, value, default)
        return default
    return value


async def _process_job(job: NotificationJob) -> None:
    payload = decode_job_payload(job)
    async with AsyncSessionLocal() as db:
        current_job = await db.get(NotificationJob, job.id)
        if current_job is None:
            return
        try:
            if current_job.job_type == JOB_TYPE_WEB_PUSH:
                await push_service.send_push_to_users(
                    db,
                    user_ids=[UUID(payload["user_id"])],
                    title=payload["title"],
                    body=payload.get("body", ""),
                    url=payload.get("url", "/"),
                    icon=payload.get("icon", "/static/icons/icon-192.png"),
                )
            elif current_job.job_type == JOB_TYPE_TELEGRAM:
                await send_telegram_message(payload["text"])
            else:
                raise ValueError(f"Unsupported notification job type: {current_job.job_type}")
        except Exception as exc:
            logger.exception("Notification job %s failed", current_job.id)
            await mark_job_failed(db, current_job, exc)
            return

        await mark_job_sent(db, current_job)
        logger.info("Notification job %s sent (%s)", current_job.id, current_job.job_type)


async def _process_batch(jobs: list[NotificationJob], concurrency: int) -> None:
    semaphore = asyncio.Semaphore(concurrency)

    async def _guarded(job: NotificationJob) -> None:
        async with semaphore:
            await _process_job(job)

    await asyncio.gather(*[_guarded(job) for job in jobs])


async def run_worker() -> None:
    batch_size = _positive_env_int("NOTIFICATION_WORKER_BATCH_SIZE", 10)
    concurrency = _positive_env_int("NOTIFICATION_WORKER_CONCURRENCY", 3)
    poll_interval = _positive_env_int("NOTIFICATION_WORKER_POLL_INTERVAL_SECONDS", 2)
    stale_after = _positive_env_int("NOTIFICATION_WORKER_STALE_AFTER_SECONDS", 300)
    worker_id = f"{socket.gethostname()}:{os.getpid()}"

    await ensure_sqlite_schema()
    logger.info(
        "Notification worker started worker_id=%s batch_size=%s concurrency=%s poll_interval=%ss",
        worker_id,
        batch_size,
        concurrency,
        poll_interval,
    )

    while True:
        try:
            async with AsyncSessionLocal() as db:
                recovered = await recover_stale_processing_jobs(db, stale_after_seconds=stale_after)
                if recovered:
                    logger.info("Recovered %s stale notification jobs", recovered)
                jobs = await claim_pending_jobs(
                    db,
                    worker_id=worker_id,
                    batch_size=batch_size,
                )

            if jobs:
                await _process_batch(jobs, concurrency=concurrency)
            else:
                await asyncio.sleep(poll_interval)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Notification worker loop failed")
            await asyncio.sleep(poll_interval)


if __name__ == "__main__":
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Notification worker stopped")
