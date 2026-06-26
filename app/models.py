import enum
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, Enum, Float, ForeignKey, Integer, String, UniqueConstraint, Uuid

from .database import Base


class MatchStatus(str, enum.Enum):
    upcoming = "upcoming"
    live = "live"
    finished = "finished"


class PointTransactionType(str, enum.Enum):
    bet_stake = "bet_stake"
    bet_reward = "bet_reward"
    bet_refund = "bet_refund"
    recharge_approved = "recharge_approved"
    admin_adjustment = "admin_adjustment"
    legacy_balance_adjustment = "legacy_balance_adjustment"


AVATAR_COLORS = [
    "#6366f1",
    "#8b5cf6",
    "#ec4899",
    "#f43f5e",
    "#f97316",
    "#eab308",
    "#22c55e",
    "#14b8a6",
    "#06b6d4",
    "#3b82f6",
    "#a855f7",
    "#84cc16",
]


import random as _random


def _random_avatar_color():
    return _random.choice(AVATAR_COLORS)


def _utc_now_naive():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String, unique=True, nullable=False, index=True)
    display_name = Column(String, nullable=True)
    total_points = Column(Integer, default=1000)
    avatar_url = Column(String, nullable=True)
    avatar_color = Column(String, nullable=True, default=_random_avatar_color)
    is_approved = Column(Boolean, nullable=False, default=False, index=True)
    approved_at = Column(DateTime, nullable=True)
    last_seen_at = Column(DateTime, nullable=True)
    previous_seen_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=_utc_now_naive)


class ProfileStatusPost(Base):
    __tablename__ = "profile_status_posts"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(String, nullable=False)
    post_type = Column(String, nullable=False, default="text")
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="SET NULL"), nullable=True, index=True)
    media_url = Column(String, nullable=True)
    media_content_type = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utc_now_naive, nullable=False, index=True)
    edited_at = Column(DateTime, nullable=True)


class ProfilePostLike(Base):
    __tablename__ = "profile_post_likes"
    __table_args__ = (
        UniqueConstraint("post_id", "user_id", name="uq_profile_post_likes_post_user"),
    )

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("profile_status_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=_utc_now_naive, nullable=False, index=True)


class ProfilePostComment(Base):
    __tablename__ = "profile_post_comments"

    id = Column(Integer, primary_key=True, index=True)
    post_id = Column(Integer, ForeignKey("profile_status_posts.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    content = Column(String, nullable=False)
    created_at = Column(DateTime, default=_utc_now_naive, nullable=False, index=True)


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True, index=True)
    home_team = Column(String, nullable=False)
    home_icon = Column(String, nullable=True)
    away_team = Column(String, nullable=False)
    away_icon = Column(String, nullable=True)
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    handicap = Column(Float, default=0.0)
    status = Column(Enum(MatchStatus), default=MatchStatus.upcoming, nullable=False)
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=True)
    resolved_at = Column(DateTime, nullable=True)


class Bet(Base):
    __tablename__ = "bets"
    __table_args__ = (
        UniqueConstraint("user_id", "match_id", name="uq_bets_user_match"),
    )

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="CASCADE"), nullable=False)
    choice = Column(String, nullable=False)
    stake = Column(Integer, nullable=False)
    taunt_text = Column(String, nullable=True)
    points_earned = Column(Integer, nullable=True, default=None)
    created_at = Column(DateTime, default=_utc_now_naive)


class PointTransaction(Base):
    __tablename__ = "point_transactions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    delta_points = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    transaction_type = Column(Enum(PointTransactionType), nullable=False, index=True)
    description = Column(String, nullable=False)
    actor_user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    bet_id = Column(Integer, ForeignKey("bets.id", ondelete="SET NULL"), nullable=True, index=True)
    match_id = Column(Integer, ForeignKey("matches.id", ondelete="SET NULL"), nullable=True, index=True)
    is_backfilled = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=_utc_now_naive, nullable=False, index=True)


class AppSetting(Base):
    __tablename__ = "app_settings"

    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)
    updated_at = Column(DateTime, default=_utc_now_naive, onupdate=_utc_now_naive)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    endpoint = Column(String, unique=True, nullable=False)
    p256dh = Column(String, nullable=False)
    auth = Column(String, nullable=False)
    user_agent = Column(String, nullable=True)
    created_at = Column(DateTime, default=_utc_now_naive)


class Notification(Base):
    """Persistent notification history shown in the bell inbox."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String, nullable=False)
    body = Column(String, nullable=False, default="")
    url = Column(String, nullable=False, default="/")
    icon = Column(String, nullable=False, default="/static/icons/icon-192.png")
    is_read = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, default=_utc_now_naive, nullable=False, index=True)
