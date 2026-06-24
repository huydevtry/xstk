"""
push_service.py — Web Push notification service using VAPID/pywebpush.

Handles:
- Sending push to a list of users (targeted, not broadcast)
- notify_match_resolved: push to users who bet on the match
- notify_post_liked: push to post owner when liked
- notify_post_commented: push to post owner + prior commenters
"""

import asyncio
import json
import logging
import os
from pathlib import Path
from typing import Sequence
from uuid import UUID

from dotenv import load_dotenv
from pywebpush import webpush, WebPushException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bet, ProfilePostComment, ProfileStatusPost, PushSubscription, User

logger = logging.getLogger(__name__)
ENV_PATH = Path(__file__).resolve().parents[2] / ".env"


def _push_env() -> tuple[str, str, str]:
    """Load VAPID config from .env lazily."""
    load_dotenv(ENV_PATH, override=False)
    private_key = os.getenv("VAPID_PRIVATE_KEY", "").strip()
    public_key = os.getenv("VAPID_PUBLIC_KEY", "").strip()
    claims_email = os.getenv("VAPID_CLAIMS_EMAIL", "mailto:admin@example.com").strip()
    return private_key, public_key, claims_email


def _send_one_push_sync(endpoint: str, p256dh: str, auth: str, payload: dict) -> bool:
    """
    Send a single push notification synchronously.
    Returns True if sent OK, False if subscription is gone (410/404).
    Raises on other errors.
    """
    private_key, _, claims_email = _push_env()
    if not private_key:
        logger.warning("VAPID_PRIVATE_KEY not configured; skipping push.")
        return True

    try:
        webpush(
            subscription_info={
                "endpoint": endpoint,
                "keys": {"p256dh": p256dh, "auth": auth},
            },
            data=json.dumps(payload, ensure_ascii=False),
            vapid_private_key=private_key,
            vapid_claims={"sub": claims_email},
            ttl=86400,  # 24 hours
        )
        return True
    except WebPushException as ex:
        if ex.response is not None and ex.response.status_code in (404, 410):
            # Subscription expired or unsubscribed
            return False
        logger.warning("WebPush send failed for %s: %s", endpoint[:40], ex)
        return True  # Keep subscription, may be transient


async def _delete_stale_subscriptions(db: AsyncSession, endpoints: list[str]) -> None:
    """Remove expired/gone subscriptions from DB."""
    if not endpoints:
        return
    for endpoint in endpoints:
        sub = (
            await db.execute(
                select(PushSubscription).where(PushSubscription.endpoint == endpoint)
            )
        ).scalars().first()
        if sub:
            await db.delete(sub)
    await db.commit()


async def send_push_to_users(
    db: AsyncSession,
    user_ids: Sequence[UUID],
    title: str,
    body: str,
    url: str = "/",
    icon: str = "/static/icons/icon-192.png",
) -> None:
    """
    Send push notification to all subscriptions belonging to the given user_ids.
    Cleans up stale (410/404) subscriptions automatically.
    """
    if not user_ids:
        return

    subscriptions = (
        await db.execute(
            select(PushSubscription).where(PushSubscription.user_id.in_(user_ids))
        )
    ).scalars().all()

    if not subscriptions:
        return

    payload = {"title": title, "body": body, "url": url, "icon": icon}
    stale_endpoints: list[str] = []

    async def _push(sub: PushSubscription) -> None:
        ok = await asyncio.to_thread(
            _send_one_push_sync, sub.endpoint, sub.p256dh, sub.auth, payload
        )
        if not ok:
            stale_endpoints.append(sub.endpoint)

    await asyncio.gather(*[_push(sub) for sub in subscriptions], return_exceptions=True)
    await _delete_stale_subscriptions(db, stale_endpoints)


# ---------------------------------------------------------------------------
# Domain-specific notification helpers
# ---------------------------------------------------------------------------

async def notify_match_resolved(
    db: AsyncSession,
    match,  # app.models.Match
    bets: list,  # list[app.models.Bet]
    users_by_id: dict,  # dict[UUID, app.models.User]
) -> None:
    """
    After a match is resolved, push personalized results to each bettor.
    bets and users_by_id are passed in (already loaded in admin.resolve_match).
    """
    try:
        match_label = f"{match.home_team} vs {match.away_team}"
        score_label = f"{match.home_score} - {match.away_score}"

        for bet in bets:
            user = users_by_id.get(bet.user_id)
            if not user:
                continue

            points_earned = bet.points_earned
            if points_earned is None:
                # Refund case
                result_msg = f"Hoàn {bet.stake:,} điểm (kèo hòa)"
                emoji = "🔄"
            elif points_earned > bet.stake:
                result_msg = f"Thắng +{points_earned - bet.stake:,} điểm 🎉"
                emoji = "🏆"
            elif points_earned == bet.stake:
                result_msg = f"Hoàn {bet.stake:,} điểm (hòa vốn)"
                emoji = "🤝"
            else:
                result_msg = f"Thua {bet.stake:,} điểm"
                emoji = "😢"

            await send_push_to_users(
                db,
                user_ids=[user.id],
                title=f"{emoji} Kết quả: {match_label}",
                body=f"{score_label} — {result_msg}",
                url="/",
            )
    except Exception:
        logger.exception("Failed to send match-resolved push notifications.")


async def notify_post_liked(
    db: AsyncSession,
    post: ProfileStatusPost,
    actor: User,
) -> None:
    """Push to post owner when someone likes their post (not self-like)."""
    try:
        if post.user_id == actor.id:
            return
        actor_name = actor.display_name or actor.email.split("@")[0]
        await send_push_to_users(
            db,
            user_ids=[post.user_id],
            title="❤️ Có người thích bài của bạn",
            body=f"{actor_name} đã thích bài viết của bạn",
            url="/community",
        )
    except Exception:
        logger.exception("Failed to send post-liked push notification.")


async def notify_post_commented(
    db: AsyncSession,
    post: ProfileStatusPost,
    actor: User,
) -> None:
    """
    Push to post owner + all prior commenters when a new comment is added.
    Excludes the actor (commenter) from recipients.
    """
    try:
        # Collect recipient user_ids: post owner + prior commenters
        prior_commenter_ids_result = await db.execute(
            select(ProfilePostComment.user_id)
            .where(ProfilePostComment.post_id == post.id)
            .distinct()
        )
        prior_commenter_ids = {row[0] for row in prior_commenter_ids_result.fetchall()}

        recipient_ids = {post.user_id} | prior_commenter_ids
        # Exclude the actor (they just commented — no self-notification)
        recipient_ids.discard(actor.id)

        if not recipient_ids:
            return

        actor_name = actor.display_name or actor.email.split("@")[0]

        # Personalize message for post owner vs other commenters
        push_tasks = []
        for uid in recipient_ids:
            if uid == post.user_id:
                title = "💬 Bình luận mới trên bài của bạn"
                body = f"{actor_name} đã bình luận vào bài của bạn"
            else:
                title = "💬 Bình luận mới"
                body = f"{actor_name} cũng bình luận vào bài này"
            push_tasks.append(
                send_push_to_users(db, user_ids=[uid], title=title, body=body, url="/community")
            )

        await asyncio.gather(*push_tasks, return_exceptions=True)
    except Exception:
        logger.exception("Failed to send post-commented push notifications.")
