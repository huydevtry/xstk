"""
push.py — API router for Web Push subscription management.

Endpoints:
  GET  /api/v1/push/vapid-public-key  — return VAPID public key for browser
  POST /api/v1/push/subscribe          — save push subscription (requires login)
  DELETE /api/v1/push/unsubscribe      — remove subscription for current user
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models import PushSubscription, User

logger = logging.getLogger(__name__)
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"

router = APIRouter()


def _vapid_public_key() -> str:
    load_dotenv(ENV_PATH, override=False)
    return os.getenv("VAPID_PUBLIC_KEY", "").strip()


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
