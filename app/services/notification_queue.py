import logging
import json
import socket
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import NotificationJob, User
from app.notifications import build_admin_new_user_pending_text

logger = logging.getLogger(__name__)


JOB_TYPE_WEB_PUSH = "web_push"
JOB_TYPE_TELEGRAM = "telegram"

STATUS_PENDING = "pending"
STATUS_PROCESSING = "processing"
STATUS_SENT = "sent"
STATUS_FAILED = "failed"

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_WEB_PUSH_ICON = "/static/icons/icon-192.png"


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _job_payload(job: NotificationJob) -> dict[str, Any]:
    return json.loads(job.payload_json or "{}")


async def enqueue_notification_job(
    db: AsyncSession,
    *,
    job_type: str,
    payload: dict[str, Any],
    recipient_user_id: UUID | None = None,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    commit: bool = True,
) -> NotificationJob:
    now = _utc_now_naive()
    job = NotificationJob(
        job_type=job_type,
        status=STATUS_PENDING,
        recipient_user_id=recipient_user_id,
        payload_json=_json_dumps(payload),
        attempts=0,
        max_attempts=max_attempts,
        next_attempt_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    if commit:
        await db.commit()
        # TEMP_NOTIFICATION_JOB_LOG: remove after enqueue timing is verified.
        print(
            "TEMP_NOTIFICATION_JOB_LOG",
            f"added_at={now.isoformat()}",
            f"id={job.id}",
            f"type={job.job_type}",
            f"recipient_user_id={job.recipient_user_id}",
            f"status={job.status}",
            flush=True,
        )
    return job


async def enqueue_web_push(
    db: AsyncSession,
    *,
    user_id: UUID,
    title: str,
    body: str,
    url: str = "/",
    icon: str = DEFAULT_WEB_PUSH_ICON,
    commit: bool = True,
) -> NotificationJob:
    return await enqueue_notification_job(
        db,
        job_type=JOB_TYPE_WEB_PUSH,
        recipient_user_id=user_id,
        payload={
            "user_id": str(user_id),
            "title": title,
            "body": body,
            "url": url,
            "icon": icon,
        },
        commit=commit,
    )


async def enqueue_telegram_message(
    db: AsyncSession,
    *,
    text: str,
    commit: bool = True,
) -> NotificationJob:
    return await enqueue_notification_job(
        db,
        job_type=JOB_TYPE_TELEGRAM,
        payload={"text": text},
        commit=commit,
    )


async def enqueue_admin_new_user_pending(db: AsyncSession, user: User) -> NotificationJob:
    return await enqueue_telegram_message(
        db,
        text=build_admin_new_user_pending_text(user),
    )


async def recover_stale_processing_jobs(
    db: AsyncSession,
    *,
    stale_after_seconds: int = 300,
) -> int:
    stale_before = _utc_now_naive() - timedelta(seconds=stale_after_seconds)
    result = await db.execute(
        update(NotificationJob)
        .where(
            NotificationJob.status == STATUS_PROCESSING,
            NotificationJob.locked_at.is_not(None),
            NotificationJob.locked_at < stale_before,
            NotificationJob.attempts < NotificationJob.max_attempts,
        )
        .values(
            status=STATUS_PENDING,
            locked_at=None,
            locked_by=None,
            updated_at=_utc_now_naive(),
        )
    )
    await db.commit()
    return int(result.rowcount or 0)


async def claim_pending_jobs(
    db: AsyncSession,
    *,
    worker_id: str | None = None,
    batch_size: int = 10,
) -> list[NotificationJob]:
    now = _utc_now_naive()
    worker_id = worker_id or socket.gethostname()
    rows = (
        await db.execute(
            select(NotificationJob)
            .where(
                NotificationJob.status == STATUS_PENDING,
                NotificationJob.attempts < NotificationJob.max_attempts,
                or_(
                    NotificationJob.next_attempt_at.is_(None),
                    NotificationJob.next_attempt_at <= now,
                ),
            )
            .order_by(NotificationJob.created_at.asc())
            .limit(batch_size)
        )
    ).scalars().all()

    for job in rows:
        job.status = STATUS_PROCESSING
        job.locked_at = now
        job.locked_by = worker_id
        job.attempts = int(job.attempts or 0) + 1
        job.updated_at = now
        db.add(job)

    await db.commit()
    if rows:
        # TEMP_NOTIFICATION_JOB_LOG: remove after enqueue timing is verified.
        print(
            "TEMP_NOTIFICATION_JOB_LOG",
            f"claimed_at={now.isoformat()}",
            f"worker_id={worker_id}",
            f"batch_size={len(rows)}",
            "job_ids=" + ",".join(str(job.id) for job in rows),
            flush=True,
        )
    return list(rows)


async def mark_job_sent(db: AsyncSession, job: NotificationJob) -> None:
    now = _utc_now_naive()
    job.status = STATUS_SENT
    job.sent_at = now
    job.updated_at = now
    job.locked_at = None
    job.locked_by = None
    db.add(job)
    await db.commit()
    # TEMP_NOTIFICATION_JOB_LOG: remove after enqueue timing is verified.
    print(
        "TEMP_NOTIFICATION_JOB_LOG",
        f"marked_sent_at={now.isoformat()}",
        f"id={job.id}",
        f"type={job.job_type}",
        f"attempts={job.attempts}",
        flush=True,
    )


async def mark_job_failed(db: AsyncSession, job: NotificationJob, exc: Exception) -> None:
    now = _utc_now_naive()
    attempts = int(job.attempts or 0)
    retry_delay = min(300, 2 ** max(0, attempts - 1))
    has_retry = attempts < int(job.max_attempts or DEFAULT_MAX_ATTEMPTS)
    job.status = STATUS_PENDING if has_retry else STATUS_FAILED
    job.next_attempt_at = now + timedelta(seconds=retry_delay) if has_retry else None
    job.last_error = str(exc)[:2000]
    job.updated_at = now
    job.locked_at = None
    job.locked_by = None
    db.add(job)
    await db.commit()


def decode_job_payload(job: NotificationJob) -> dict[str, Any]:
    return _job_payload(job)
