"""
push.py — API router for Web Push subscription management.

Endpoints:
  GET    /api/v1/push/vapid-public-key      — return VAPID public key for browser
  POST   /api/v1/push/subscribe             — save push subscription (requires login)
  DELETE /api/v1/push/unsubscribe           — remove subscription for current user
  GET    /api/v1/push/latest-notification   — fetch pending notification (called by SW)
  GET    /api/v1/push/status                — whether current user has active push sub
  GET    /api/v1/notifications              — list recent notifications for inbox
  POST   /api/v1/notifications/read-all     — mark all notifications as read
"""

import logging
import os
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import Notification, PushSubscription, User

logger = logging.getLogger(__name__)
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

router = APIRouter()


def _vapid_public_key() -> str:
    load_dotenv(ENV_PATH, override=False)
    return os.getenv("VAPID_PUBLIC_KEY", "").strip()


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class PushSubscribePayload(BaseModel):
    endpoint: str
    p256dh: str
    auth: str
    user_agent: str | None = None


class PushUnsubscribePayload(BaseModel):
    endpoint: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get("/api/v1/push/vapid-public-key")
async def get_vapid_public_key():
    """Return the VAPID public key so the browser can subscribe."""
    key = _vapid_public_key()
    if not key:
        raise HTTPException(status_code=503, detail="Push notifications not configured.")
    return {"public_key": key}


@router.post("/api/v1/push/subscribe", status_code=201)
async def subscribe_push(
    payload: PushSubscribePayload,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Save (or update) a push subscription for the current user.
    If the same endpoint already exists for this user, update keys in-place.
    If the endpoint exists for a different user, replace it.
    """
    existing = (
        await db.execute(
            select(PushSubscription).where(PushSubscription.endpoint == payload.endpoint)
        )
    ).scalars().first()

    if existing:
        # Update keys and ownership
        existing.user_id = user.id
        existing.p256dh = payload.p256dh
        existing.auth = payload.auth
        existing.user_agent = payload.user_agent or request.headers.get("user-agent")
        db.add(existing)
    else:
        sub = PushSubscription(
            user_id=user.id,
            endpoint=payload.endpoint,
            p256dh=payload.p256dh,
            auth=payload.auth,
            user_agent=payload.user_agent or request.headers.get("user-agent"),
        )
        db.add(sub)

    await db.commit()
    return {"status": "subscribed"}


@router.delete("/api/v1/push/unsubscribe")
async def unsubscribe_push(
    payload: PushUnsubscribePayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Remove a specific push subscription for the current user."""
    await db.execute(
        delete(PushSubscription).where(
            PushSubscription.user_id == user.id,
            PushSubscription.endpoint == payload.endpoint,
        )
    )
    await db.commit()
    return {"status": "unsubscribed"}


@router.get("/api/v1/push/latest-notification")
async def get_latest_notification(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Called by the Service Worker after receiving an empty push.
    Returns the newest undelivered notification payload for this user and marks it delivered.
    Returns 204 No Content if there is nothing pending (SW should stay silent).
    """
    notification = (
        await db.execute(
            select(Notification)
            .where(
                Notification.user_id == user.id,
                Notification.delivered_at.is_(None),
            )
            .order_by(Notification.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if not notification:
        return Response(status_code=204)

    notification.delivered_at = _utc_now_naive()
    db.add(notification)
    await db.commit()

    return {
        "title": notification.title,
        "body": notification.body,
        "url": notification.url,
        "icon": notification.icon,
    }


@router.get("/api/v1/push/status")
async def get_push_status(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return whether the current user has at least one active push subscription."""
    sub = (
        await db.execute(
            select(PushSubscription).where(PushSubscription.user_id == user.id).limit(1)
        )
    ).scalars().first()
    return {"subscribed": sub is not None}


# ---------------------------------------------------------------------------
# Notification inbox endpoints
# ---------------------------------------------------------------------------

@router.get("/api/v1/notifications")
async def list_notifications(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Return the 30 most recent notifications for the current user."""
    rows = (
        await db.execute(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(30)
        )
    ).scalars().all()

    unread_count = sum(1 for n in rows if not n.is_read)

    return {
        "unread_count": unread_count,
        "notifications": [
            {
                "id": n.id,
                "title": n.title,
                "body": n.body,
                "url": n.url,
                "is_read": n.is_read,
                "created_at": n.created_at.isoformat() if n.created_at else None,
            }
            for n in rows
        ],
    }


@router.post("/api/v1/notifications/read-all", status_code=204)
async def mark_all_read(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark all notifications for the current user as read."""
    from sqlalchemy import update
    await db.execute(
        update(Notification)
        .where(Notification.user_id == user.id, Notification.is_read == False)  # noqa: E712
        .values(is_read=True)
    )
    await db.commit()


@router.post("/api/v1/notifications/{notification_id}/read", status_code=204)
async def mark_one_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Mark a single notification as read (only if it belongs to the current user)."""
    from sqlalchemy import update
    await db.execute(
        update(Notification)
        .where(
            Notification.id == notification_id,
            Notification.user_id == user.id,
            Notification.is_read == False,  # noqa: E712
        )
        .values(is_read=True)
    )
    await db.commit()
