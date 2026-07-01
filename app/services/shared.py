from fastapi import Depends, HTTPException, UploadFile, File, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.requests import Request
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, case, desc, delete, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import aliased
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from pydantic import BaseModel, Field
from typing import Literal, Optional
import logging
import hashlib
import random
import uuid as uuid_lib
from uuid import UUID
from pathlib import Path
from decimal import Decimal, ROUND_DOWN
from collections import defaultdict
import html
import os
import re
import json
from urllib.parse import urlparse

from app.database import Base, get_db
from app.models import (
    Match,
    MatchStatus,
    Bet,
    User,
    ProfileStatusPost,
    ProfilePostLike,
    ProfilePostComment,
    PointTransaction,
    PointTransactionType,
    AppSetting,
)
from app.dependencies import get_current_user, get_admin_user, get_request_user, ADMIN_EMAILS, LOCAL_DEV_AUTH, LOCAL_DEV_EMAIL

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="templates")

ASSET_VERSION = str(
    max(
        int(Path("static/css/style.css").stat().st_mtime),
        int(Path("static/css/betting-taunt.css").stat().st_mtime),
        int(Path("static/js/app.js").stat().st_mtime),
        int(Path("static/js/app-taunt.js").stat().st_mtime),
        int(Path("static/js/admin.js").stat().st_mtime),
        int(Path("static/js/community.js").stat().st_mtime),
        int(Path("static/js/giphy-picker.js").stat().st_mtime),
        int(Path("static/js/match-detail.js").stat().st_mtime),
        int(Path("static/js/profile.js").stat().st_mtime),
        int(Path("static/js/timeline.js").stat().st_mtime),
        int(Path("static/js/user-menu.js").stat().st_mtime),
        int(Path("static/js/user-shell.js").stat().st_mtime),
    )
)

NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
    "Surrogate-Control": "no-store",
}

CHOICE_LABELS = {"HOME": "Chủ nhà", "DRAW": "Hòa", "AWAY": "Khách"}

OUTCOME_LABELS = {
    "WIN": "Thắng",
    "LOSE": "Thua",
    "REFUND": "Hoàn điểm",
    "HALF_WIN": "Thắng nửa",
    "HALF_LOSE": "Thua nửa",
    "PENDING": "Chờ kết quả",
}

MATCH_DEFAULT_DURATION = timedelta(hours=2)

APP_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

MAX_PROFILE_NAME_LENGTH = 30

MAX_TAUNT_LENGTH = 30

MAX_PROFILE_STATUS_LENGTH = 160

MAX_PROFILE_COMMENT_LENGTH = 280

MAX_FEED_MEDIA_SIZE_BYTES = 8 * 1024 * 1024

MAX_PROFILE_TIMELINE_ITEMS = 20

DEFAULT_PROFILE_TIMELINE_PAGE_SIZE = 10

MAX_PROFILE_TIMELINE_PAGE_SIZE = 20

MAX_HOMEPAGE_ANNOUNCEMENT_LENGTH = 280

PROFILE_POST_TYPE_TEXT = "text"

PROFILE_POST_TYPE_MATCH_REACTION = "match_reaction"

PROFILE_POST_TYPE_AVATAR_UPDATE = "avatar_update"

DEFAULT_POINT_TRANSACTION_PAGE_SIZE = 20

MAX_POINT_TRANSACTION_PAGE_SIZE = 50

POINT_TRANSACTIONS_BACKFILL_KEY = "point_transactions_backfill_version"

POINT_TRANSACTIONS_BACKFILL_VERSION = "admin_seed_v3_no_recharge"

LOGOUT_URL = "https://learning.huydevtry.com/cdn-cgi/access/logout"

GIPHY_API_KEY = os.getenv("GIPHY_API_KEY", "").strip()

COUNTRY_CODE_PATH = Path("data/country_code.json")

COUNTRY_CODE_MAP: dict[str, str] = json.loads(COUNTRY_CODE_PATH.read_text(encoding="utf-8"))

COUNTRY_CODE_OPTIONS = [
    {"code": code.upper(), "name": name}
    for code, name in COUNTRY_CODE_MAP.items()
]

def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

def _logout_url_for_request(request: Request) -> Optional[str]:
    return LOGOUT_URL

def _is_admin_viewer(user: Optional[User]) -> bool:
    if user is None:
        return False
    return user.email.strip().lower() in ADMIN_EMAILS

def _page_context(
    request: Request,
    *,
    current_page: str,
    viewer: Optional[User] = None,
    **extra: object,
) -> dict[str, object]:
    context: dict[str, object] = {
        "request": request,
        "asset_version": ASSET_VERSION,
        "logout_url": _logout_url_for_request(request),
        "current_page": current_page,
        "viewer_is_admin": _is_admin_viewer(viewer),
        "giphy_api_key": GIPHY_API_KEY,
    }
    context.update(extra)
    return context

def _serialize_utc_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    aware = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    return aware.astimezone(APP_TIMEZONE).isoformat()

def _serialize_app_datetime(value: Optional[datetime]) -> Optional[str]:
    if value is None:
        return None
    aware = value.replace(tzinfo=APP_TIMEZONE) if value.tzinfo is None else value.astimezone(APP_TIMEZONE)
    return aware.astimezone(APP_TIMEZONE).isoformat()

def _format_coins(value: int) -> str:
    return f"{int(value):,}d"

def _provided_fields(payload: BaseModel) -> set[str]:
    fields = getattr(payload, "model_fields_set", None)
    if fields is not None:
        return set(fields)
    legacy_fields = getattr(payload, "__fields_set__", set())
    return set(legacy_fields)

def _normalize_display_name(value: Optional[str]) -> str:
    name = (value or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="Ten hien thi khong duoc de trong.")
    if len(name) > MAX_PROFILE_NAME_LENGTH:
        raise HTTPException(status_code=400, detail=f"Ten hien thi toi da {MAX_PROFILE_NAME_LENGTH} ky tu.")
    return name

def _normalize_optional_taunt(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > MAX_TAUNT_LENGTH:
        raise HTTPException(status_code=400, detail=f"Câu gáy tối đa {MAX_TAUNT_LENGTH} ký tự.")
    return text

def _normalize_optional_profile_status(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None
    if len(text) > MAX_PROFILE_STATUS_LENGTH:
        raise HTTPException(status_code=400, detail=f"Trạng thái tối đa {MAX_PROFILE_STATUS_LENGTH} ký tự.")
    return text

def _normalize_profile_comment(value: str) -> str:
    text = (value or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="Bình luận không được để trống.")
    if len(text) > MAX_PROFILE_COMMENT_LENGTH:
        raise HTTPException(status_code=400, detail=f"Bình luận tối đa {MAX_PROFILE_COMMENT_LENGTH} ký tự.")
    return text

def _normalize_timeline_limit(limit: int) -> int:
    return max(1, min(limit, MAX_PROFILE_TIMELINE_PAGE_SIZE))

def _normalize_point_transaction_limit(limit: int) -> int:
    return max(1, min(limit, MAX_POINT_TRANSACTION_PAGE_SIZE))

def _decimal_handicap(value: float | Decimal | int) -> Decimal:
    return Decimal(str(value)).quantize(Decimal("0.01"))

def _is_two_way_handicap(handicap: float | Decimal | int) -> bool:
    return _decimal_handicap(handicap) % 1 != 0

def _is_quarter_handicap(handicap: float | Decimal | int) -> bool:
    fraction = abs(_decimal_handicap(handicap)) % 1
    return fraction in {Decimal("0.25"), Decimal("0.75")}

def _handicap_component_lines(handicap: float | Decimal | int) -> list[Decimal]:
    line = _decimal_handicap(handicap)
    if _is_quarter_handicap(line):
        quarter = Decimal("0.25")
        return [line - quarter, line + quarter]
    return [line]

def _two_way_component_result(
    *,
    home_score: int,
    away_score: int,
    handicap_line: Decimal,
    choice: str,
) -> str:
    adjusted_home = Decimal(home_score) + handicap_line
    adjusted_away = Decimal(away_score)
    if adjusted_home > adjusted_away:
        winner = "HOME"
    elif adjusted_home < adjusted_away:
        winner = "AWAY"
    else:
        winner = None

    if winner is None:
        return "REFUND"
    return "WIN" if choice == winner else "LOSE"

def _outcome_from_component_results(component_results: list[str]) -> str:
    unique = set(component_results)
    if unique == {"REFUND"}:
        return "REFUND"
    if unique == {"WIN"}:
        return "WIN"
    if unique == {"LOSE"}:
        return "LOSE"
    if unique == {"WIN", "REFUND"}:
        return "HALF_WIN"
    if unique == {"LOSE", "REFUND"}:
        return "HALF_LOSE"
    return "PENDING"

def _resolve_market_winning_choice(match: Match) -> str:
    adjusted_home = match.home_score + match.handicap
    adjusted_away = match.away_score
    if adjusted_home > adjusted_away:
        return "HOME"
    if adjusted_home < adjusted_away:
        return "AWAY"
    return "DRAW"

def _derive_bet_outcome(match: Match, bet: Bet) -> str:
    if not _match_result_published(match):
        return "PENDING"
    if bet.points_earned is None:
        return "REFUND"

    if _is_two_way_handicap(match.handicap) and bet.choice in {"HOME", "AWAY"}:
        component_results = [
            _two_way_component_result(
                home_score=match.home_score,
                away_score=match.away_score,
                handicap_line=line,
                choice=bet.choice,
            )
            for line in _handicap_component_lines(match.handicap)
        ]
        return _outcome_from_component_results(component_results)

    winner = _resolve_market_winning_choice(match)
    return "WIN" if bet.choice == winner else "LOSE"

def _compute_two_way_settlement(match: Match, bets: list[Bet]) -> dict:
    component_lines = _handicap_component_lines(match.handicap)
    divisor = Decimal(len(component_lines))
    exact_returns: dict[int, Decimal] = {bet.id: Decimal("0") for bet in bets if bet.id is not None}
    component_results: dict[int, list[str]] = {bet.id: [] for bet in bets if bet.id is not None}

    for handicap_line in component_lines:
        stake_parts = {
            bet.id: Decimal(bet.stake) / divisor
            for bet in bets
            if bet.id is not None
        }
        total_pool = sum(stake_parts.values(), Decimal("0"))
        natural_results = {
            bet.id: _two_way_component_result(
                home_score=match.home_score,
                away_score=match.away_score,
                handicap_line=handicap_line,
                choice=bet.choice,
            )
            for bet in bets
            if bet.id is not None
        }
        winner_ids = [
            bet_id
            for bet_id, result in natural_results.items()
            if result == "WIN"
        ]

        if not winner_ids:
            for bet_id, stake_part in stake_parts.items():
                component_results[bet_id].append("REFUND")
                exact_returns[bet_id] += stake_part
            continue

        total_winner_stake = sum((stake_parts[bet_id] for bet_id in winner_ids), Decimal("0"))
        for bet_id, result in natural_results.items():
            component_results[bet_id].append(result)
            if result == "WIN":
                exact_returns[bet_id] += (total_pool * stake_parts[bet_id]) / total_winner_stake
            elif result == "REFUND":
                exact_returns[bet_id] += stake_parts[bet_id]

    allocated_returns = {
        bet_id: int(value.to_integral_value(rounding=ROUND_DOWN))
        for bet_id, value in exact_returns.items()
    }
    total_allocated = sum(allocated_returns.values())
    total_stake = sum(int(bet.stake) for bet in bets)
    remainder = max(0, total_stake - total_allocated)
    fractional_items = sorted(
        (
            (exact_returns[bet.id] - Decimal(allocated_returns[bet.id]), bet.created_at, bet.id)
            for bet in bets
            if bet.id is not None
        ),
        key=lambda item: (-item[0], item[1], item[2]),
    )
    for index in range(remainder):
        _, _, bet_id = fractional_items[index]
        allocated_returns[bet_id] += 1

    payout_by_bet_id: dict[int, Optional[int]] = {}
    outcome_by_bet_id: dict[int, str] = {}
    for bet in bets:
        if bet.id is None:
            continue
        outcome = _outcome_from_component_results(component_results[bet.id])
        payout = allocated_returns[bet.id]
        payout_by_bet_id[bet.id] = None if outcome == "REFUND" and payout == int(bet.stake) else payout
        outcome_by_bet_id[bet.id] = outcome

    return {
        "payout_by_bet_id": payout_by_bet_id,
        "outcome_by_bet_id": outcome_by_bet_id,
        "refunded": bool(bets) and all(outcome == "REFUND" for outcome in outcome_by_bet_id.values()),
    }

def _serialize_profile_status_match(match: Optional[Match]) -> Optional[dict]:
    if match is None:
        return None
    return {
        "id": match.id,
        "home_team": match.home_team,
        "home_icon": match.home_icon,
        "away_team": match.away_team,
        "away_icon": match.away_icon,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "status": match.status,
        "result_published": bool(getattr(match, "resolved_at", None)),
    }

def _serialize_match_reaction_result(
    *,
    bet: Optional[Bet],
    match: Optional[Match],
) -> Optional[dict]:
    if bet is None or match is None or not _match_result_published(match):
        return None
    outcome = _derive_bet_outcome(match, bet)
    return {
        "outcome": outcome.lower(),
        "outcome_label": OUTCOME_LABELS.get(outcome, "Chờ kết quả"),
        "points_earned": bet.points_earned,
        "stake": bet.stake,
    }

def _serialize_profile_status_media(post: ProfileStatusPost) -> Optional[dict]:
    media_url = getattr(post, "media_url", None)
    media_content_type = getattr(post, "media_content_type", None)
    if not media_url or not media_content_type:
        return None
    parsed = urlparse(media_url)
    host = (parsed.netloc or "").lower()
    provider = "giphy" if host == "giphy.com" or host.endswith(".giphy.com") else None
    return {
        "url": media_url,
        "content_type": media_content_type,
        "kind": "gif" if media_content_type == "image/gif" else "image",
        "provider": provider,
    }

def _serialize_profile_post_comment(comment: ProfilePostComment, author: User) -> dict:
    return {
        "id": comment.id,
        "content": comment.content,
        "created_at": _serialize_utc_datetime(comment.created_at),
        "author": _user_avatar_payload(author),
    }

def _serialize_profile_status_post(
    post: ProfileStatusPost,
    *,
    author: Optional[User] = None,
    author_badge: Optional[dict] = None,
    match: Optional[Match] = None,
    bet: Optional[Bet] = None,
    viewer_user_id: Optional[UUID] = None,
    like_count: int = 0,
    viewer_liked: bool = False,
    liked_users: Optional[list[dict]] = None,
    comment_count: int = 0,
    comments: Optional[list[dict]] = None,
) -> dict:
    edited_at = getattr(post, "edited_at", None)
    post_type = post.post_type or PROFILE_POST_TYPE_TEXT
    can_edit = (
        post_type != PROFILE_POST_TYPE_AVATAR_UPDATE
        and viewer_user_id is not None
        and post.user_id == viewer_user_id
    )
    author_payload = _user_avatar_payload(author) if author is not None else None
    if author_payload is not None:
        author_payload["badge"] = author_badge

    return {
        "id": post.id,
        "post_type": post_type,
        "content": post.content,
        "media": _serialize_profile_status_media(post),
        "created_at": _serialize_utc_datetime(post.created_at),
        "edited_at": _serialize_utc_datetime(edited_at),
        "is_edited": edited_at is not None,
        "can_edit": can_edit,
        "author": author_payload,
        "match": _serialize_profile_status_match(match),
        "reaction_result": _serialize_match_reaction_result(bet=bet, match=match)
        if post_type == PROFILE_POST_TYPE_MATCH_REACTION
        else None,
        "like_count": int(like_count or 0),
        "viewer_liked": bool(viewer_liked),
        "liked_users": liked_users or [],
        "comment_count": int(comment_count or 0),
        "comments": comments or [],
    }

async def _get_profile_post_interactions(
    db: AsyncSession,
    post_ids: list[int],
    *,
    viewer_user_id: Optional[UUID] = None,
    comments_per_post: Optional[int] = None,
) -> dict[int, dict]:
    if not post_ids:
        return {}

    interactions = {
        post_id: {
            "like_count": 0,
            "viewer_liked": False,
            "liked_users": [],
            "comment_count": 0,
            "comments": [],
        }
        for post_id in post_ids
    }

    like_rows = (
        await db.execute(
            select(ProfilePostLike.post_id, func.count(ProfilePostLike.id).label("cnt"))
            .join(User, ProfilePostLike.user_id == User.id)
            .where(ProfilePostLike.post_id.in_(post_ids), User.is_approved.is_(True))
            .group_by(ProfilePostLike.post_id)
        )
    ).all()
    for row in like_rows:
        interactions[row.post_id]["like_count"] = int(row.cnt or 0)

    liked_user_rows = (
        await db.execute(
            select(ProfilePostLike.post_id, ProfilePostLike.created_at, User)
            .join(User, ProfilePostLike.user_id == User.id)
            .where(ProfilePostLike.post_id.in_(post_ids), User.is_approved.is_(True))
            .order_by(ProfilePostLike.post_id.asc(), ProfilePostLike.created_at.desc())
        )
    ).all()
    for row in liked_user_rows:
        user_payload = _user_avatar_payload(row.User)
        user_payload["liked_at"] = _serialize_utc_datetime(row.created_at)
        interactions[row.post_id]["liked_users"].append(user_payload)

    if viewer_user_id is not None:
        liked_post_ids = {
            post_id
            for post_id, in (
                await db.execute(
                    select(ProfilePostLike.post_id).where(
                        ProfilePostLike.post_id.in_(post_ids),
                        ProfilePostLike.user_id == viewer_user_id,
                    )
                )
            ).all()
        }
        for post_id in liked_post_ids:
            if post_id in interactions:
                interactions[post_id]["viewer_liked"] = True

    comment_count_rows = (
        await db.execute(
            select(ProfilePostComment.post_id, func.count(ProfilePostComment.id).label("cnt"))
            .join(User, ProfilePostComment.user_id == User.id)
            .where(ProfilePostComment.post_id.in_(post_ids), User.is_approved.is_(True))
            .group_by(ProfilePostComment.post_id)
        )
    ).all()
    for row in comment_count_rows:
        interactions[row.post_id]["comment_count"] = int(row.cnt or 0)

    comment_rows = (
        await db.execute(
            select(ProfilePostComment, User)
            .join(User, ProfilePostComment.user_id == User.id)
            .where(ProfilePostComment.post_id.in_(post_ids), User.is_approved.is_(True))
            .order_by(
                ProfilePostComment.post_id.asc(),
                ProfilePostComment.created_at.desc(),
                ProfilePostComment.id.desc(),
            )
        )
    ).all()
    comments_by_post: dict[int, list[dict]] = {post_id: [] for post_id in post_ids}
    for row in comment_rows:
        post_comments = comments_by_post.setdefault(row.ProfilePostComment.post_id, [])
        if comments_per_post is not None and len(post_comments) >= comments_per_post:
            continue
        post_comments.append(_serialize_profile_post_comment(row.ProfilePostComment, row.User))

    for post_id, comments in comments_by_post.items():
        interactions[post_id]["comments"] = list(reversed(comments))

    return interactions

async def _list_profile_status_posts(
    db: AsyncSession,
    *,
    user_id: Optional[UUID] = None,
    viewer_user_id: Optional[UUID] = None,
    post_id: Optional[int] = None,
    offset: int = 0,
    limit: int = DEFAULT_PROFILE_TIMELINE_PAGE_SIZE,
) -> dict:
    safe_offset = max(0, offset)
    safe_limit = _normalize_timeline_limit(limit)
    query = (
        select(ProfileStatusPost, User, Match, Bet)
        .join(User, ProfileStatusPost.user_id == User.id)
        .outerjoin(Match, ProfileStatusPost.match_id == Match.id)
        .outerjoin(
            Bet,
            (ProfileStatusPost.user_id == Bet.user_id)
            & (ProfileStatusPost.match_id == Bet.match_id),
        )
        .where(User.is_approved.is_(True))
    )
    if user_id is not None:
        query = query.where(ProfileStatusPost.user_id == user_id)
    if post_id is not None:
        query = query.where(ProfileStatusPost.id == post_id)
        # Profile timeline: sort by post creation time
        query = query.order_by(
            desc(ProfileStatusPost.created_at), desc(ProfileStatusPost.id)
        )
    else:
        # Community timeline: sort by latest comment time
        latest_comment_time = (
            select(func.max(ProfilePostComment.created_at))
            .where(ProfilePostComment.post_id == ProfileStatusPost.id)
            .correlate(ProfileStatusPost)
            .scalar_subquery()
        )
        query = query.order_by(
            desc(func.coalesce(latest_comment_time, ProfileStatusPost.created_at)),
            desc(ProfileStatusPost.id)
        )

    query = (
        query
        .offset(safe_offset)
        .limit(safe_limit + 1)
    )
    rows = (await db.execute(query)).all()
    page_rows = rows[:safe_limit]
    author_badges = await _build_user_badges_for_users(db)
    interactions = await _get_profile_post_interactions(
        db,
        [row.ProfileStatusPost.id for row in page_rows],
        viewer_user_id=viewer_user_id,
    )
    items = [
        _serialize_profile_status_post(
            row.ProfileStatusPost,
            author=row.User,
            author_badge=author_badges.get(row.User.id),
            match=row.Match,
            bet=row.Bet,
            viewer_user_id=viewer_user_id,
            **interactions.get(row.ProfileStatusPost.id, {}),
        )
        for row in page_rows
    ]
    next_offset = safe_offset + safe_limit if len(rows) > safe_limit else None
    return {
        "items": items,
        "next_offset": next_offset,
    }

async def _get_profile_status_timeline(
    db: AsyncSession,
    user_id: UUID,
    *,
    viewer_user_id: Optional[UUID] = None,
    limit: int = MAX_PROFILE_TIMELINE_ITEMS,
) -> list[dict]:
    page = await _list_profile_status_posts(
        db,
        user_id=user_id,
        viewer_user_id=viewer_user_id,
        offset=0,
        limit=min(limit, MAX_PROFILE_TIMELINE_ITEMS),
    )
    return page["items"]


async def _get_latest_profile_status_content(
    db: AsyncSession,
    user_id: UUID,
) -> Optional[str]:
    query = (
        select(ProfileStatusPost.content)
        .where(
            ProfileStatusPost.user_id == user_id,
            ProfileStatusPost.post_type != PROFILE_POST_TYPE_AVATAR_UPDATE,
            func.trim(func.coalesce(ProfileStatusPost.content, "")) != "",
        )
        .order_by(desc(ProfileStatusPost.created_at), desc(ProfileStatusPost.id))
        .limit(1)
    )
    return (await db.execute(query)).scalars().first()


async def _create_profile_status_post(
    db: AsyncSession,
    user: User,
    content: str,
    *,
    created_at: Optional[datetime] = None,
    post_type: str = PROFILE_POST_TYPE_TEXT,
    match: Optional[Match] = None,
    media_url: Optional[str] = None,
    media_content_type: Optional[str] = None,
    update_profile_status: bool = True,
    ) -> ProfileStatusPost:
    post = ProfileStatusPost(
        user_id=user.id,
        content=content,
        post_type=post_type,
        match_id=match.id if match is not None else None,
        media_url=media_url,
        media_content_type=media_content_type,
        created_at=created_at or _utc_now_naive(),
    )
    db.add(post)
    return post

async def _has_match_reaction_post(
    db: AsyncSession,
    *,
    user_id: UUID,
    match_id: int,
) -> bool:
    existing = (
        await db.execute(
            select(ProfileStatusPost.id)
            .where(
                ProfileStatusPost.user_id == user_id,
                ProfileStatusPost.match_id == match_id,
                ProfileStatusPost.post_type == PROFILE_POST_TYPE_MATCH_REACTION,
            )
            .limit(1)
        )
    ).scalar()
    return existing is not None

async def _backfill_profile_status_timeline(db: AsyncSession) -> None:
    return None

def _local_now_naive() -> datetime:
    """Return app-local time as naive datetime for match schedule comparisons."""
    return datetime.now(APP_TIMEZONE).replace(tzinfo=None)

def _render_inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"\*(.+?)\*", r"<em>\1</em>", escaped)
    return escaped

def render_markdown(md_text: str) -> str:
    lines = md_text.splitlines()
    parts: list[str] = []
    list_items: list[str] = []

    def flush_list() -> None:
        nonlocal list_items
        if list_items:
            parts.append("<ul class=\"my-4 list-disc pl-6 space-y-2\">")
            parts.extend(list_items)
            parts.append("</ul>")
            list_items = []

    def flush_paragraph(paragraph_lines: list[str]) -> None:
        if not paragraph_lines:
            return
        paragraph = " ".join(s.strip() for s in paragraph_lines).strip()
        if paragraph:
            parts.append(f"<p class=\"my-4\">{_render_inline_markdown(paragraph)}</p>")

    paragraph_lines: list[str] = []

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph(paragraph_lines)
            paragraph_lines = []
            flush_list()
            continue

        heading_match = re.match(r"^(#{1,3})\s+(.*)$", stripped)
        if heading_match:
            flush_paragraph(paragraph_lines)
            paragraph_lines = []
            flush_list()
            level = len(heading_match.group(1))
            content = _render_inline_markdown(heading_match.group(2).strip())
            heading_classes = {
                1: "mt-0 mb-5 text-3xl md:text-4xl font-black leading-tight text-slate-950",
                2: "mt-8 mb-4 text-2xl md:text-3xl font-black leading-tight text-slate-950",
                3: "mt-6 mb-3 text-xl md:text-2xl font-extrabold leading-tight text-slate-950",
            }
            parts.append(f"<h{level} class=\"{heading_classes[level]}\">{content}</h{level}>")
            continue

        if stripped in {"---", "***", "___"}:
            flush_paragraph(paragraph_lines)
            paragraph_lines = []
            flush_list()
            parts.append("<hr class=\"my-6 border-slate-200\" />")
            continue

        list_match = re.match(r"^[*-]\s+(.*)$", stripped)
        if list_match:
            flush_paragraph(paragraph_lines)
            paragraph_lines = []
            item_html = _render_inline_markdown(list_match.group(1).strip())
            list_items.append(f"<li class=\"leading-7\">{item_html}</li>")
            continue

        if stripped.startswith("1. "):
            flush_paragraph(paragraph_lines)
            paragraph_lines = []
            flush_list()
            parts.append(
                f"<ol class=\"my-4 list-decimal pl-6 space-y-2\"><li class=\"leading-7\">{_render_inline_markdown(stripped[3:].strip())}</li></ol>"
            )
            continue

        flush_list()
        paragraph_lines.append(stripped)

    flush_paragraph(paragraph_lines)
    flush_list()
    return "\n".join(parts)

DEFAULT_FEATURE_SETTINGS = {
    "points_enabled": "1",
    "homepage_announcement": "",
}

def _parse_bool_setting(value: Optional[str], default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}

async def _ensure_default_settings(db: AsyncSession) -> None:
    existing = (await db.execute(select(AppSetting))).scalars().all()
    existing_keys = {item.key for item in existing}
    existing_values = {item.key: item.value for item in existing}
    changed = False
    for key, value in DEFAULT_FEATURE_SETTINGS.items():
        if key not in existing_keys:
            if key == "points_enabled":
                value = "1" if (
                    _parse_bool_setting(existing_values.get("topup_enabled"), True)
                    and _parse_bool_setting(existing_values.get("exchange_enabled"), True)
                ) else "0"
            db.add(AppSetting(key=key, value=value))
            changed = True
    if changed:
        await db.commit()

async def _get_app_setting(db: AsyncSession, key: str) -> Optional[AppSetting]:
    return (
        await db.execute(select(AppSetting).where(AppSetting.key == key))
    ).scalars().first()

async def _set_app_setting(db: AsyncSession, key: str, value: str) -> None:
    setting = await _get_app_setting(db, key)
    if not setting:
        setting = AppSetting(key=key, value=value)
    else:
        setting.value = value
    db.add(setting)

def _is_refund_backfill_case(match: Optional[Match], bet: Bet, positive_payout_match_ids: set[int]) -> bool:
    return (
        match is not None
        and match.status == MatchStatus.finished
        and bool(match.resolved_at)
        and bet.points_earned is None
        and match.id not in positive_payout_match_ids
    )

async def _backfill_point_transactions(db: AsyncSession) -> None:
    await _ensure_default_settings(db)
    version_setting = await _get_app_setting(db, POINT_TRANSACTIONS_BACKFILL_KEY)
    if version_setting and (version_setting.value or "").strip() == POINT_TRANSACTIONS_BACKFILL_VERSION:
        return

    await db.execute(delete(PointTransaction).where(PointTransaction.is_backfilled.is_(True)))

    users = {
        user.id: user
        for user in (await db.execute(select(User))).scalars().all()
    }
    matches = {
        match.id: match
        for match in (await db.execute(select(Match))).scalars().all()
    }
    bets = (
        await db.execute(
            select(Bet).order_by(Bet.created_at.asc(), Bet.id.asc())
        )
    ).scalars().all()
    positive_payout_match_ids = {
        match_id
        for match_id, in (
            await db.execute(
                select(Bet.match_id)
                .where(Bet.points_earned > 0)
                .distinct()
            )
        ).all()
        if match_id is not None
    }

    bettor_ids = {
        user_id
        for user_id, in (
            await db.execute(select(Bet.user_id).distinct())
        ).all()
        if user_id is not None
    }
    bets_by_user: dict[UUID, list[Bet]] = {}
    for bet in bets:
        bets_by_user.setdefault(bet.user_id, []).append(bet)

    for user_id in bettor_ids:
        user = users.get(user_id)
        if user is None:
            continue

        events: list[dict] = []
        delta_sum = 0

        for bet in bets_by_user.get(user_id, []):
            match = matches.get(bet.match_id)
            stake_delta = -int(bet.stake)
            delta_sum += stake_delta
            events.append(
                {
                    "created_at": bet.created_at or user.created_at or _utc_now_naive(),
                    "delta": stake_delta,
                    "transaction_type": PointTransactionType.bet_stake,
                    "description": f"Backfill: đặt cược: {match.home_team} vs {match.away_team}" if match else "Backfill: đặt cược",
                    "actor_user_id": None,
                    "bet_id": bet.id,
                    "match_id": bet.match_id,
                }
            )

            if bet.points_earned is not None and int(bet.points_earned) > 0:
                reward_delta = int(bet.points_earned)
                delta_sum += reward_delta
                events.append(
                    {
                        "created_at": (match.resolved_at if match else None) or bet.created_at or user.created_at or _utc_now_naive(),
                        "delta": reward_delta,
                        "transaction_type": PointTransactionType.bet_reward,
                        "description": f"Backfill: thưởng cược: {match.home_team} vs {match.away_team}" if match else "Backfill: thưởng cược",
                        "actor_user_id": None,
                        "bet_id": bet.id,
                        "match_id": bet.match_id,
                    }
                )
            elif _is_refund_backfill_case(match, bet, positive_payout_match_ids):
                refund_delta = int(bet.stake)
                delta_sum += refund_delta
                events.append(
                    {
                        "created_at": (match.resolved_at if match else None) or bet.created_at or user.created_at or _utc_now_naive(),
                        "delta": refund_delta,
                        "transaction_type": PointTransactionType.bet_refund,
                        "description": f"Backfill: hoàn điểm: {match.home_team} vs {match.away_team}" if match else "Backfill: hoàn điểm",
                        "actor_user_id": None,
                        "bet_id": bet.id,
                        "match_id": bet.match_id,
                    }
                )

        events.sort(key=lambda item: (item["created_at"], item["delta"] > 0, item["bet_id"] or 0))
        if not events:
            continue

        initial_admin_delta = int(user.total_points or 0) - delta_sum
        first_event_time = events[0]["created_at"] or user.created_at or _utc_now_naive()
        seed_time = min(first_event_time, user.created_at or first_event_time) - timedelta(seconds=1)
        if initial_admin_delta != 0:
            transaction_type = PointTransactionType.admin_adjustment if initial_admin_delta > 0 else PointTransactionType.legacy_balance_adjustment
            description = (
                "Backfill: admin cộng điểm khởi tạo lịch sử"
                if initial_admin_delta > 0
                else "Backfill: điều chỉnh lịch sử"
            )
            events.insert(
                0,
                {
                    "created_at": seed_time,
                    "delta": initial_admin_delta,
                    "transaction_type": transaction_type,
                    "description": description,
                    "actor_user_id": None,
                    "bet_id": None,
                    "match_id": None,
                }
            )

        balance = 0
        for item in events:
            balance += int(item["delta"])
            db.add(
                PointTransaction(
                    user_id=user_id,
                    delta_points=int(item["delta"]),
                    balance_after=balance,
                    transaction_type=item["transaction_type"],
                    description=item["description"],
                    actor_user_id=item["actor_user_id"],
                    bet_id=item["bet_id"],
                    match_id=item["match_id"],
                    is_backfilled=True,
                    created_at=item["created_at"],
                )
            )

    await _set_app_setting(db, POINT_TRANSACTIONS_BACKFILL_KEY, POINT_TRANSACTIONS_BACKFILL_VERSION)
    await db.commit()

async def _get_feature_settings(db: AsyncSession) -> dict[str, object]:
    await _ensure_default_settings(db)
    settings = (await db.execute(select(AppSetting))).scalars().all()
    value_map = {item.key: item.value for item in settings}
    legacy_topup = _parse_bool_setting(value_map.get("topup_enabled"), True)
    legacy_exchange = _parse_bool_setting(value_map.get("exchange_enabled"), True)
    return {
        "points_enabled": _parse_bool_setting(
            value_map.get("points_enabled"),
            legacy_topup and legacy_exchange,
        ),
        "homepage_announcement": (value_map.get("homepage_announcement") or "").strip(),
    }

def _match_effective_end_time(match: Match) -> datetime:
    return match.end_time or (match.start_time + MATCH_DEFAULT_DURATION)

async def _get_match_min_stake(db: AsyncSession, match_id: int) -> Optional[int]:
    return (
        await db.execute(
            select(func.min(Bet.stake)).where(Bet.match_id == match_id)
        )
    ).scalar_one()

async def _sync_match_statuses(db: AsyncSession) -> int:
    """Promote matches based on start/end times."""
    now = _local_now_naive()
    rows = (await db.execute(
        select(Match).where(Match.status != MatchStatus.finished)
    )).scalars().all()

    changed = 0
    for match in rows:
        if match.end_time is None:
            match.end_time = match.start_time + MATCH_DEFAULT_DURATION
            changed += 1
        if match.status == MatchStatus.upcoming and now >= match.start_time:
            match.status = MatchStatus.live
            changed += 1
        if match.status == MatchStatus.live and now >= match.end_time:
            match.status = MatchStatus.finished
            changed += 1

    if changed:
        await db.commit()
    return changed

async def _get_user_by_id(db: AsyncSession, user_id: str) -> User:
    try:
        parsed_id = uuid_lib.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại.")

    user = (
        await db.execute(
            select(User).where(User.id == parsed_id, User.is_approved.is_(True))
        )
    ).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại.")
    return user

AVATARS_DIR = Path("static/avatars")

FEED_MEDIA_DIR = Path("static/feed-media")

AVATAR_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}

FEED_UPLOAD_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
}

def _detect_image_content_type(contents: bytes) -> Optional[str]:
    if contents.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if contents.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(contents) >= 12 and contents[:4] == b"RIFF" and contents[8:12] == b"WEBP":
        return "image/webp"
    return None

def _local_media_path(media_url: Optional[str], directory: Path) -> Optional[Path]:
    url = (media_url or "").strip()
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    root = directory.resolve()
    candidate = Path(parsed.path.lstrip("/")).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        return None
    return candidate

def _delete_local_media_file(media_url: Optional[str], directory: Path) -> bool:
    path = _local_media_path(media_url, directory)
    if path is None or not path.is_file():
        return False
    path.unlink(missing_ok=True)
    return True

async def _delete_unused_feed_media(
    db: AsyncSession,
    media_url: Optional[str],
    *,
    exclude_post_id: Optional[int] = None,
) -> bool:
    path = _local_media_path(media_url, FEED_MEDIA_DIR)
    if path is None:
        return False

    query = select(func.count(ProfileStatusPost.id)).where(ProfileStatusPost.media_url == media_url)
    if exclude_post_id is not None:
        query = query.where(ProfileStatusPost.id != exclude_post_id)
    reference_count = (await db.execute(query)).scalar() or 0
    if reference_count:
        return False

    if path.is_file():
        path.unlink(missing_ok=True)
        return True
    return False

def _save_feed_media_bytes(
    contents: bytes,
    content_type: str,
    *,
    allowed_content_types: Optional[dict[str, str]] = None,
    max_bytes: int = MAX_FEED_MEDIA_SIZE_BYTES,
) -> dict:
    safe_content_type = (content_type or "").split(";", 1)[0].strip().lower()
    allowed = allowed_content_types or FEED_UPLOAD_CONTENT_TYPES
    if safe_content_type not in allowed:
        raise HTTPException(status_code=400, detail="Định dạng ảnh không được hỗ trợ.")
    if len(contents) > max_bytes:
        raise HTTPException(status_code=400, detail="Ảnh quá lớn.")

    detected_type = _detect_image_content_type(contents)
    if detected_type != safe_content_type:
        raise HTTPException(status_code=400, detail="Nội dung file không khớp định dạng ảnh.")

    FEED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
    ext = allowed[safe_content_type]
    filename = f"{uuid_lib.uuid4().hex}.{ext}"
    dest = FEED_MEDIA_DIR / filename
    dest.write_bytes(contents)

    return {
        "url": f"/static/feed-media/{filename}",
        "content_type": safe_content_type,
    }

async def _save_feed_media_file(file: UploadFile) -> dict:
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in FEED_UPLOAD_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận ảnh JPG, PNG, WebP. GIF chỉ được chọn từ GIPHY.")

    contents = await file.read()
    return _save_feed_media_bytes(contents, content_type)

def _normalize_external_media_payload(media_url: Optional[str], media_provider: Optional[str]) -> Optional[dict]:
    url = (media_url or "").strip()
    if not url:
        return None

    provider = (media_provider or "").strip().lower()
    if provider != "giphy":
        raise HTTPException(status_code=400, detail="Nguồn GIF không được hỗ trợ.")

    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if parsed.scheme not in {"http", "https"} or not host:
        raise HTTPException(status_code=400, detail="URL GIF không hợp lệ.")
    if not (host == "giphy.com" or host.endswith(".giphy.com")):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận GIF từ GIPHY.")
    if not parsed.path.lower().endswith(".gif"):
        raise HTTPException(status_code=400, detail="Liên kết GIPHY phải là file GIF hợp lệ.")

    return {
        "url": url,
        "content_type": "image/gif",
        "provider": provider,
    }

def _match_result_published(match: Match) -> bool:
    return match.status == MatchStatus.finished and bool(getattr(match, "resolved_at", None))

def _match_display_score(match: Match) -> str:
    if (
        getattr(match, "home_penalty_score", None) is not None
        and getattr(match, "away_penalty_score", None) is not None
    ):
        return f"{match.home_score} ({match.home_penalty_score}) - {match.away_score} ({match.away_penalty_score})"
    return f"{match.home_score} - {match.away_score}"

def _match_response(match: Match):
    return {
        "id": match.id,
        "home_team": match.home_team,
        "home_icon": match.home_icon,
        "away_team": match.away_team,
        "away_icon": match.away_icon,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "home_penalty_score": getattr(match, "home_penalty_score", None),
        "away_penalty_score": getattr(match, "away_penalty_score", None),
        "handicap": match.handicap,
        "round_label": getattr(match, "round_label", None),
        "status": match.status,
        "start_time": _serialize_app_datetime(match.start_time),
        "end_time": _serialize_app_datetime(_match_effective_end_time(match)) if match.start_time else None,
        "result_published": _match_result_published(match),
        "resolved_at": _serialize_app_datetime(match.resolved_at) if getattr(match, "resolved_at", None) else None,
    }

def _choice_label(choice: Optional[str]) -> str:
    return CHOICE_LABELS.get(choice or "", choice or "Không rõ")

def _user_display_name(user: User) -> str:
    return user.display_name or user.email.split("@")[0]

def _user_initials(user: User) -> str:
    return _user_display_name(user)[:2].upper()

def _user_avatar_payload(user: User) -> dict:
    display_name = _user_display_name(user)
    return {
        "id": str(user.id),
        "name": display_name,
        "display_name": display_name,
        "avatar_url": user.avatar_url,
        "avatar_color": user.avatar_color or "#6366f1",
        "initials": _user_initials(user),
    }

def _point_transaction_type_label(value: PointTransactionType | str | None) -> str:
    mapping = {
        PointTransactionType.bet_stake: "Đặt cược",
        PointTransactionType.bet_reward: "Thưởng cược",
        PointTransactionType.bet_refund: "Hoàn điểm",
        PointTransactionType.recharge_approved: "Điều chỉnh lịch sử",
        PointTransactionType.admin_adjustment: "Điều chỉnh admin",
        PointTransactionType.legacy_balance_adjustment: "Điều chỉnh lịch sử",
    }
    return mapping.get(value, str(value or "Giao dịch"))

async def _record_point_transaction(
    db: AsyncSession,
    *,
    user: User,
    delta_points: int,
    balance_after: Optional[int] = None,
    transaction_type: PointTransactionType,
    description: str,
    actor: Optional[User] = None,
    bet: Optional[Bet] = None,
    match: Optional[Match] = None,
    is_backfilled: bool = False,
    created_at: Optional[datetime] = None,
) -> PointTransaction:
    transaction = PointTransaction(
        user_id=user.id,
        delta_points=int(delta_points),
        balance_after=int(user.total_points if balance_after is None else balance_after),
        transaction_type=transaction_type,
        description=description.strip(),
        actor_user_id=actor.id if actor is not None else None,
        bet_id=bet.id if bet is not None else None,
        match_id=match.id if match is not None else (bet.match_id if bet is not None else None),
        is_backfilled=is_backfilled,
        created_at=created_at or _utc_now_naive(),
    )
    db.add(transaction)
    return transaction

def _serialize_point_transaction(
    transaction: PointTransaction,
    *,
    actor: Optional[User] = None,
    bet: Optional[Bet] = None,
    match: Optional[Match] = None,
) -> dict:
    description = transaction.description
    if transaction.transaction_type == PointTransactionType.recharge_approved:
        description = "Điều chỉnh lịch sử"
    actor_payload = None
    if actor is not None:
        actor_payload = {
            "id": str(actor.id),
            "display_name": _user_display_name(actor),
            "email": actor.email,
        }
    bet_payload = None
    if bet is not None:
        bet_payload = {
            "id": bet.id,
            "match_id": bet.match_id,
            "choice": bet.choice,
            "stake": bet.stake,
        }
    match_payload = None
    if match is not None:
        match_payload = {
            "id": match.id,
            "home_team": match.home_team,
            "away_team": match.away_team,
            "home_icon": match.home_icon,
            "away_icon": match.away_icon,
        }
    return {
        "id": transaction.id,
        "transaction_type": transaction.transaction_type,
        "transaction_type_label": _point_transaction_type_label(transaction.transaction_type),
        "delta_points": transaction.delta_points,
        "balance_after": transaction.balance_after,
        "description": description,
        "created_at": _serialize_utc_datetime(transaction.created_at),
        "is_backfilled": bool(transaction.is_backfilled),
        "actor": actor_payload,
        "bet": bet_payload,
        "match": match_payload,
    }

async def _list_point_transactions(
    db: AsyncSession,
    *,
    user_id: UUID,
    offset: int = 0,
    limit: int = DEFAULT_POINT_TRANSACTION_PAGE_SIZE,
) -> dict:
    safe_offset = max(0, offset)
    safe_limit = _normalize_point_transaction_limit(limit)
    actor_alias = aliased(User)
    rows = (
        await db.execute(
            select(PointTransaction, actor_alias, Bet, Match)
            .outerjoin(actor_alias, PointTransaction.actor_user_id == actor_alias.id)
            .outerjoin(Bet, PointTransaction.bet_id == Bet.id)
            .outerjoin(Match, PointTransaction.match_id == Match.id)
            .where(PointTransaction.user_id == user_id)
            .order_by(desc(PointTransaction.created_at), desc(PointTransaction.id))
            .offset(safe_offset)
            .limit(safe_limit + 1)
        )
    ).all()
    page_rows = rows[:safe_limit]
    items = [
        _serialize_point_transaction(
            row.PointTransaction,
            actor=row[1],
            bet=row.Bet,
            match=row.Match,
        )
        for row in page_rows
    ]
    next_offset = safe_offset + safe_limit if len(rows) > safe_limit else None
    return {"items": items, "next_offset": next_offset}

async def _get_match_reaction_match_ids(
    db: AsyncSession,
    *,
    user_id: UUID,
    match_ids: list[int],
) -> set[int]:
    if not match_ids:
        return set()
    rows = (
        await db.execute(
            select(ProfileStatusPost.match_id)
            .where(
                ProfileStatusPost.user_id == user_id,
                ProfileStatusPost.post_type == PROFILE_POST_TYPE_MATCH_REACTION,
                ProfileStatusPost.match_id.in_(match_ids),
            )
            .distinct()
        )
    ).scalars().all()
    return {match_id for match_id in rows if match_id is not None}

def _serialize_bet_history_entry(
    *,
    bet: Bet,
    match: Match,
    can_share_reaction: bool,
    has_shared_reaction: bool,
    can_edit_stake: bool = False,
) -> dict:
    outcome = _derive_bet_outcome(match, bet)
    return {
        "bet_id": bet.id,
        "match_id": match.id,
        "home_team": match.home_team,
        "home_icon": match.home_icon,
        "away_team": match.away_team,
        "away_icon": match.away_icon,
        "match_status": match.status,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "home_penalty_score": getattr(match, "home_penalty_score", None),
        "away_penalty_score": getattr(match, "away_penalty_score", None),
        "handicap": match.handicap,
        "round_label": getattr(match, "round_label", None),
        "start_time": _serialize_app_datetime(match.start_time),
        "choice": bet.choice,
        "stake": bet.stake,
        "taunt_text": bet.taunt_text,
        "points_earned": bet.points_earned,
        "outcome": outcome,
        "outcome_label": OUTCOME_LABELS.get(outcome, "Chờ kết quả"),
        "reward_label": _format_reward_label(outcome, bet.stake, bet.points_earned),
        "created_at": _serialize_utc_datetime(bet.created_at),
        "result_published": _match_result_published(match),
        "can_edit_taunt": match.status == MatchStatus.upcoming,
        "can_edit_stake": can_edit_stake,
        "can_share_reaction": can_share_reaction,
        "has_shared_reaction": has_shared_reaction,
    }

USER_BADGE_DEFINITIONS = [
    ("sleeping", {"label": "Ngủ đông", "emoji": "💤", "color": "gray"}),
    ("missing", {"label": "Mất tích bí ẩn", "emoji": "🕵️", "color": "gray"}),
    ("rich", {"label": "Đại gia", "emoji": "🤑", "color": "gold"}),
    ("bottom", {"label": "Báo thủ", "emoji": "🐣", "color": "gray"}),
    ("hot_streak", {"label": "Phong độ hủy diệt", "emoji": "🔥", "color": "red"}),
    ("comeback", {"label": "Người về bờ", "emoji": "🌊", "color": "purple"}),
    ("salvation", {"label": "Cứu rỗi", "emoji": "🙏", "color": "red"}),
    ("hard_hunter", {"label": "Thợ săn kèo khó", "emoji": "🎯", "color": "purple"}),
    ("prophet", {"label": "Nhà tiên tri", "emoji": "🔮", "color": "purple"}),
    ("money_printer", {"label": "Máy in 10đ", "emoji": "🖨️", "color": "gold"}),
    ("small_ball", {"label": "Góp gió thành bão", "emoji": "🌱", "color": "gray"}),
    ("newbie", {"label": "Tân binh máu lửa", "emoji": "⚡", "color": "gold"}),
    ("veteran", {"label": "Lão làng", "emoji": "🎖️", "color": "gold"}),
    ("steady", {"label": "Dân chơi đều tay", "emoji": "📅", "color": "gray"}),
    ("taunter", {"label": "Chuyên gia cà khịa", "emoji": "📣", "color": "purple"}),
    ("reporter", {"label": "Nhà báo sau trận", "emoji": "📰", "color": "gray"}),
    ("awake", {"label": "Vừa tỉnh dậy", "emoji": "☕", "color": "gold"}),
    ("slight_risk", {"label": "Liều nhẹ", "emoji": "🎲", "color": "red"}),
    ("community", {"label": "Hòa nhập cộng đồng", "emoji": "🤝", "color": "purple"}),
]

USER_BADGE_BY_KEY = {key: payload for key, payload in USER_BADGE_DEFINITIONS}
USER_BADGE_PRIORITY = {key: idx for idx, (key, _) in enumerate(USER_BADGE_DEFINITIONS)}


def _user_badge_payload(badge_key: Optional[str]) -> Optional[dict]:
    if not badge_key:
        return None
    payload = USER_BADGE_BY_KEY.get(badge_key)
    return dict(payload) if payload else None


def _select_distributed_user_badges(
    candidate_badges_by_user: dict[UUID, list[str]],
    ordered_user_ids: list[UUID],
) -> dict[UUID, str]:
    selected_by_user: dict[UUID, str] = {}
    selected_counts: dict[str, int] = {}

    for user_id in ordered_user_ids:
        candidates = [
            badge_key
            for badge_key in candidate_badges_by_user.get(user_id, [])
            if badge_key in USER_BADGE_PRIORITY
        ]
        if not candidates:
            continue

        selected = min(
            candidates,
            key=lambda badge_key: (
                selected_counts.get(badge_key, 0),
                USER_BADGE_PRIORITY[badge_key],
            ),
        )
        selected_by_user[user_id] = selected
        selected_counts[selected] = selected_counts.get(selected, 0) + 1

    return selected_by_user


def _is_contrarian_win(bet: Bet, match_choice_counts: dict[int, dict[str, int]]) -> bool:
    counts = match_choice_counts.get(bet.match_id, {})
    if sum(counts.values()) < 5:
        return False

    my_count = counts.get(bet.choice, 0)
    all_counts = list(counts.values())
    return bool(all_counts and my_count == min(all_counts) and my_count < max(all_counts))


def _candidate_badges_for_user(
    user: User,
    *,
    rank: int,
    total_users: int,
    bets: list[Bet],
    match_choice_counts: dict[int, dict[str, int]],
    reaction_count: int,
    top_24h_user_ids: set[UUID],
    now: datetime,
) -> list[str]:
    candidates: list[str] = []
    resolved_bets = [bet for bet in bets if bet.points_earned is not None]
    recent_resolved = sorted(resolved_bets, key=lambda bet: bet.created_at, reverse=True)
    winning_bets = [bet for bet in resolved_bets if int(bet.points_earned or 0) > 0]
    contrarian_wins = sum(1 for bet in winning_bets if _is_contrarian_win(bet, match_choice_counts))
    taunt_count = sum(1 for bet in bets if (bet.taunt_text or "").strip())
    week_ago = now - timedelta(days=7)
    recent_bet_days = {
        bet.created_at.date()
        for bet in bets
        if bet.created_at is not None and bet.created_at >= week_ago
    }
    approved_at = user.approved_at or user.created_at
    last_seen_at = user.last_seen_at
    previous_seen_at = user.previous_seen_at

    if last_seen_at is not None and last_seen_at <= now - timedelta(days=7):
        candidates.append("sleeping")
    if last_seen_at is not None and last_seen_at <= now - timedelta(days=2):
        candidates.append("missing")
    if rank == 1:
        candidates.append("rich")
    if rank == total_users and len(resolved_bets) >= 3:
        candidates.append("bottom")
    if len(recent_resolved) >= 3 and all(int(bet.points_earned or 0) > 0 for bet in recent_resolved[:3]):
        candidates.append("hot_streak")
    if (
        len(recent_resolved) >= 3
        and int(recent_resolved[0].points_earned or 0) > 0
        and all(int(bet.points_earned or 0) == 0 for bet in recent_resolved[1:3])
    ):
        candidates.append("comeback")
    if len(recent_resolved) >= 3 and all(int(bet.points_earned or 0) == 0 for bet in recent_resolved[:3]):
        candidates.append("salvation")
    if contrarian_wins >= 2:
        candidates.append("hard_hunter")
    if contrarian_wins >= 1:
        candidates.append("prophet")
    if user.id in top_24h_user_ids:
        candidates.append("money_printer")
    if resolved_bets:
        average_stake = sum(int(bet.stake or 0) for bet in resolved_bets) / len(resolved_bets)
        net_points = sum(int(bet.points_earned or 0) - int(bet.stake or 0) for bet in resolved_bets)
        if len(resolved_bets) >= 8 and average_stake <= 10 and net_points > 0:
            candidates.append("small_ball")
    if approved_at is not None and approved_at > now - timedelta(days=7) and len(bets) >= 3:
        candidates.append("newbie")
    if approved_at is not None and approved_at <= now - timedelta(days=7) and len(bets) >= 10:
        candidates.append("veteran")
    if len(recent_bet_days) >= 3:
        candidates.append("steady")
    if taunt_count >= 5:
        candidates.append("taunter")
    if reaction_count >= 3:
        candidates.append("reporter")
    if (
        previous_seen_at is not None
        and last_seen_at is not None
        and last_seen_at - previous_seen_at >= timedelta(days=2)
        and any(bet.created_at >= now - timedelta(hours=24) for bet in bets)
    ):
        candidates.append("awake")
    if any(int(bet.stake or 0) > 10 for bet in bets):
        candidates.append("slight_risk")
    if reaction_count >= 1 and taunt_count >= 1:
        candidates.append("community")

    return candidates

async def _build_user_badges_for_users(db: AsyncSession) -> dict[UUID, dict]:
    ordered_users = (
        await db.execute(
            select(User)
            .where(User.is_approved.is_(True))
            .order_by(desc(User.total_points), User.id.asc())
        )
    ).scalars().all()
    total_users = len(ordered_users)
    if not total_users:
        return {}

    ordered_ids = [ordered_user.id for ordered_user in ordered_users]
    ranks_by_user_id = {uid: idx + 1 for idx, uid in enumerate(ordered_ids)}

    all_bets = (
        await db.execute(
            select(Bet)
            .where(Bet.user_id.in_(ordered_ids))
            .order_by(Bet.user_id.asc(), Bet.created_at.desc())
        )
    ).scalars().all()
    bets_by_user_id: dict[UUID, list[Bet]] = defaultdict(list)
    match_choice_counts: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    now = _utc_now_naive()
    since_24h = now - timedelta(hours=24)
    earned_24h_by_user_id: dict[UUID, int] = defaultdict(int)

    for bet in all_bets:
        bets_by_user_id[bet.user_id].append(bet)
        match_choice_counts[bet.match_id][bet.choice] += 1
        if bet.created_at >= since_24h and bet.points_earned is not None and int(bet.points_earned or 0) > 0:
            earned_24h_by_user_id[bet.user_id] += int(bet.points_earned or 0)

    max_earned_24h = max(earned_24h_by_user_id.values(), default=0)
    top_24h_user_ids = {
        uid
        for uid, earned in earned_24h_by_user_id.items()
        if earned == max_earned_24h and earned >= 10
    }

    reaction_rows = (
        await db.execute(
            select(ProfileStatusPost.user_id, func.count(ProfileStatusPost.id).label("cnt"))
            .where(
                ProfileStatusPost.user_id.in_(ordered_ids),
                ProfileStatusPost.post_type == PROFILE_POST_TYPE_MATCH_REACTION,
            )
            .group_by(ProfileStatusPost.user_id)
        )
    ).all()
    reaction_count_by_user_id = {row.user_id: int(row.cnt) for row in reaction_rows}

    candidate_badges_by_user = {
        ordered_user.id: _candidate_badges_for_user(
            ordered_user,
            rank=ranks_by_user_id[ordered_user.id],
            total_users=total_users,
            bets=bets_by_user_id.get(ordered_user.id, []),
            match_choice_counts=match_choice_counts,
            reaction_count=reaction_count_by_user_id.get(ordered_user.id, 0),
            top_24h_user_ids=top_24h_user_ids,
            now=now,
        )
        for ordered_user in ordered_users
    }
    selected_badges_by_user = _select_distributed_user_badges(candidate_badges_by_user, ordered_ids)
    return {
        user_id: payload
        for user_id, badge_key in selected_badges_by_user.items()
        if (payload := _user_badge_payload(badge_key)) is not None
    }


async def _build_user_badge_for_profile(user: User, db: AsyncSession) -> Optional[dict]:
    return (await _build_user_badges_for_users(db)).get(user.id)

def _stable_pick(options, seed: str) -> str:
    if not options:
        return ""
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return options[int(digest, 16) % len(options)]

def _format_reward_label(outcome: str, stake: int, points_earned: Optional[int]) -> str:
    if outcome in {"WIN", "HALF_WIN", "HALF_LOSE"}:
        return f"Nhận {_format_coins(int(points_earned or 0))}"
    if outcome == "LOSE":
        return "0d"
    if outcome == "REFUND":
        return f"Hoàn {_format_coins(int(stake))}"
    return "Chờ kết quả"

def _build_detail_quote(
    *,
    match: Match,
    choice: str,
    outcome: str,
    stake: int,
    points_earned: Optional[int],
    winning_choice: Optional[str],
    name: str,
) -> str:
    choice_text = _choice_label(choice)
    winner_text = _choice_label(winning_choice)
    quote_bank = {
        "WIN": [
            "{name} ôm đúng cửa {choice}. Hôm nay bảng điểm phải tự chỉnh lại thái độ.",
            "{name} chọn {choice} chuẩn như xem trước kết quả. Đám đông xin phép học theo.",
            "{name} vào kèo {choice} rất gọn. Trận này trực giác đã thắng tranh cãi.",
        ],
        "HALF_WIN": [
            "{name} đi cửa {choice} và ăn nửa kèo rất tỉnh. Chưa phải đại thắng, nhưng đủ để nói chuyện bằng nụ cười.",
            "{name} ôm {choice} đúng nhịp để thắng nửa. Không ồn ào, chỉ là lời lãi đến vừa đẹp.",
            "{name} chọn {choice} và lấy về nửa chiến công. Kèo này thắng không trọn nhưng gáy vẫn có cơ sở.",
        ],
        "LOSE": [
            "{name} chọn {choice} khá tự tin, nhưng kết quả lại trả lời theo kiểu rất thẳng.",
            "{name} vừa trải nghiệm một pha kèo không chiều lòng niềm tin.",
            "{name} đi cửa {choice} hơi sớm một nhịp. Hôm nay trực giác xin nghỉ phép.",
        ],
        "HALF_LOSE": [
            "{name} đi cửa {choice} và chỉ mất nửa kèo. Có đau, nhưng vẫn còn lý do để làm lại.",
            "{name} ôm {choice} chưa tới mức trắng tay. Trận này đời chỉ thu học phí một nửa.",
            "{name} vừa trải qua cú thua nửa khá lửng lơ. Không vui, nhưng chưa đến mức phải tắt máy đi ngủ.",
        ],
        "REFUND": [
            "{name} gặp kèo hoàn điểm. Ít ra ví vẫn nguyên, tinh thần cũng đỡ đau.",
            "{name} đi một vòng rồi quay lại vạch xuất phát. Trận này công bằng đến mức hơi buồn cười.",
            "{name} không mất điểm nhưng cũng chưa kịp trêu ai. Kèo này đúng kiểu hòa cho tất cả.",
        ],
        "PENDING": [
            "{name} đang chờ kèo nổ. Cửa {choice} mà lên tiếng thì câu chuyện sẽ vui hơn nhiều.",
            "{name} đã vào cửa {choice}, giờ chỉ còn chờ bảng điểm quyết định phần hài hước.",
            "{name} chọn {choice}, còn trận đấu thì giữ kịch tính khá lâu.",
        ],
    }
    seed = f"{match.id}:{name}:{choice}:{outcome}:{stake}:{points_earned or 0}:{winning_choice or ''}"
    template = _stable_pick(quote_bank.get(outcome, quote_bank["PENDING"]), seed)
    return template.format(name=name, choice=choice_text, winner=winner_text, stake=_format_coins(stake))

def _build_headline_quote(
    *,
    match: Match,
    settlement: dict,
    summary: dict,
) -> str:
    if settlement.get("is_finished") and not settlement.get("result_published"):
        return _stable_pick(
            [
                "Trận đã khép lại theo lịch, hiện đang chờ công bố kết quả chính thức.",
                "90 phút đã qua, nhưng bảng điểm vẫn còn chờ cú nhấp chuột từ admin.",
                "Kèo đã hết giờ, kết quả vẫn đang được giữ ở trạng thái chờ xác nhận.",
                "Trận này đã chốt giờ thi đấu, còn tỉ số thì đợi người có quyền công bố.",
                "Người chơi tạm đứng xem, vì kết quả chính thức vẫn chưa được mở khóa.",
            ],
            f"{match.id}:pending_result",
        )

    if settlement["is_finished"]:
        if settlement["refunded"]:
            return _stable_pick(
                [
                    "Kèo này hoàn tiền, nên ai cũng rời bàn với vẻ mặt khá lịch sự.",
                    "Trận đã xong nhưng không cửa nào đủ lực để giữ lại màn khịa dài lâu.",
                    "Không ai ăn đủ, thế là cuộc vui tạm dừng trong thế cân bằng hơi buồn cười.",
                    "Tưởng thế nào, đá hùng hục 90 phút xong trả lại tiền. Quần áo ai nấy mặc, nhà ai nấy về.",
                    "Cả làng huề vốn! Những kẻ mạnh miệng nhất trước giờ lăn bóng nay bỗng trở nên hiền lành lạ thường.",
                    "Một trận cầu tốn calo của cầu thủ và tốn cả thanh xuân của người xem. Chốt lại: Huề tiền!",
                    "Hệ thống trả lại tiền đây, anh em cất đi mai chơi tiếp, nay chưa ai đủ tư cách gáy đâu.",
                    "Điểm về lại ví, tình anh em chưa rạn nứt. Hôm nay vũ trụ độ cho cả nhóm khỏi mất tiền đấy.",
                    "Nhìn bảng điểm im lìm mà thấy thương. Chuẩn bị văn mẫu khịa nhau cả ngày xong cuối cùng phải xóa vội.",
                    "Tiền vẫn trong túi, đồng nghiệp vẫn nhìn mặt nhau. Một cái kết nhạt nhẽo nhưng an toàn!",
                    "Hòa cả làng! Thôi anh em thu dọn hiện trường, nay không có ai ra đê cũng chẳng ai lên đỉnh."
                ],
                f"{match.id}:refund",
            )

        winner_choice = settlement["winning_choice"] or "HOME"
        winner_text = _choice_label(winner_choice)
        return _stable_pick(
            [
                "{winner} đã lên tiếng. Người ôm đúng cửa hôm nay nói ít nhưng cười nhiều.",
                "Kết quả ngả về {winner}. Bên kia chỉ còn cách tự an ủi bằng kinh nghiệm.",
                "{winner} thắng trận này, và đám đông vừa học thêm một bài về niềm tin.",
                "Chúc mừng các cổ đông {winner}. Nhận tiền đi kìa, tiền lấy từ túi anh em tiêu lúc nào cũng sướng.",
                "{winner} chốt hạ! Những ai nằm cửa này xin phép được gáy to từ giờ đến sáng mai.",
                "Hệ thống đang chuyển tiền từ những trái tim tan vỡ sang cho fan {winner}. Đề nghị bên thua không khóc.",
                "90 phút bão táp kết thúc với chiến thắng cho {winner}. Mấy anh nằm cửa ngược chắc đang lẳng lặng xóa văn mẫu.",
                "Ánh sáng chân lý hôm nay gọi tên {winner}. Bên kia đá xước cả móng chân cũng không gánh nổi sổ đỏ của anh em.",
                "Tiếng thở dài của đám đông làm nền cho nụ cười của người chọn {winner}. Bóng đá mà, cay lắm!",
                "{winner} mang tiền về cho mẹ, còn đội bạn thì mang nợ về cho anh em.",
                "Ai bảo cờ bạc là may rủi? Nhìn mấy anh trúng quả {winner} kìa, toàn 'phân tích chiến thuật' cả đấy!",
                "Quyết định thuộc về {winner}. Người ăn thì vỗ đùi đen đét, kẻ thua thì lại bắt đầu bài ca đổ tại VAR."
            ],
            f"{match.id}:{winner_choice}",
        ).format(
            winner=winner_text,
            home=match.home_team,
            away=match.away_team,
            score=f"{match.home_score}-{match.away_score}",
        )

    dominant_choice = sorted(
        summary.items(),
        key=lambda item: (-item[1]["stake"], -item[1]["count"], item[0]),
    )[0][0]
    dominant_text = _choice_label(dominant_choice)
    return _stable_pick(
        [
            "Cửa {choice} đang đông khách nhất. Đám đông đang chờ xem ai sẽ cười sau cùng.",
            "Quỹ đang nghiêng về {choice}. Trận này nhìn là biết sẽ còn nhiều lời ra tiếng vào.",
            "{choice} đang được chú ý nhất, nhưng bảng điểm thì vẫn thích tạo bất ngờ.",
        ],
        f"{match.id}:pending:{dominant_choice}",
    ).format(
        choice=dominant_text,
        home=match.home_team,
        away=match.away_team,
    )

async def _build_match_detail_payload(
    *,
    match: Match,
    user: User,
    db: AsyncSession,
):
    query = (
        select(Bet, User)
        .join(User, Bet.user_id == User.id)
        .where(Bet.match_id == match.id, User.is_approved.is_(True))
        .order_by(Bet.created_at.asc())
    )
    rows = (await db.execute(query)).all()

    summary = {
        "HOME": {"stake": 0, "count": 0},
        "DRAW": {"stake": 0, "count": 0},
        "AWAY": {"stake": 0, "count": 0},
    }
    bettors = {"HOME": [], "DRAW": [], "AWAY": []}

    for row in rows:
        choice = row.Bet.choice
        summary[choice]["stake"] += row.Bet.stake
        summary[choice]["count"] += 1

    is_finished = match.status == MatchStatus.finished
    result_published = is_finished and bool(match.resolved_at)
    adjusted_home = None
    adjusted_away = None
    winning_choice = None
    if result_published:
        adjusted_home = match.home_score + match.handicap
        adjusted_away = match.away_score
        if adjusted_home > adjusted_away:
            winning_choice = "HOME"
        elif adjusted_home < adjusted_away:
            winning_choice = "AWAY"
        else:
            winning_choice = "DRAW"

    total_pool = sum(summary[ch]["stake"] for ch in summary)
    stakes_on_winner = summary[winning_choice]["stake"] if winning_choice else 0
    has_bets = bool(rows)
    refunded = result_published and has_bets and all(row.Bet.points_earned is None for row in rows)

    settlement = {
        "is_finished": is_finished,
        "result_published": result_published,
        "winning_choice": winning_choice if result_published else None,
        "winning_choice_label": _choice_label(winning_choice) if result_published else None,
        "adjusted_home_score": adjusted_home if result_published else None,
        "adjusted_away_score": adjusted_away if result_published else None,
        "adjusted_score": f"{adjusted_home}-{adjusted_away}" if result_published else None,
        "score": _match_display_score(match) if result_published else None,
        "refunded": refunded,
        "winner_count": 0,
        "loser_count": 0,
        "refund_count": 0,
        "headline_quote": None,
    }

    for row in rows:
        outcome = _derive_bet_outcome(match, row.Bet)

        if outcome in {"WIN", "HALF_WIN"}:
            settlement["winner_count"] += 1
        elif outcome in {"LOSE", "HALF_LOSE"}:
            settlement["loser_count"] += 1
        elif outcome == "REFUND":
            settlement["refund_count"] += 1

        user_payload = _user_avatar_payload(row.User)
        bettors[row.Bet.choice].append({
            **user_payload,
            "stake": row.Bet.stake,
            "created_at": _serialize_utc_datetime(row.Bet.created_at),
            "is_lone_wolf": summary[row.Bet.choice]["count"] == 1 and max(
                summary[ch]["count"] for ch in summary if ch != row.Bet.choice
            ) >= 3,
            "outcome": outcome,
            "outcome_label": OUTCOME_LABELS[outcome],
            "quote": _build_detail_quote(
                match=match,
                choice=row.Bet.choice,
                outcome=outcome,
                stake=row.Bet.stake,
                points_earned=row.Bet.points_earned,
                winning_choice=winning_choice if result_published else None,
                name=user_payload["name"],
            ),
            "reward_label": _format_reward_label(outcome, row.Bet.stake, row.Bet.points_earned),
            "points_earned": row.Bet.points_earned,
        })

    my_row = next((row for row in rows if row.User.id == user.id), None)
    my_bet = None
    if my_row:
        my_outcome = _derive_bet_outcome(match, my_row.Bet)

        my_bet = {
            "bet_id": my_row.Bet.id,
            "choice": my_row.Bet.choice,
            "stake": my_row.Bet.stake,
            "taunt_text": my_row.Bet.taunt_text,
            "points_earned": my_row.Bet.points_earned,
            "created_at": _serialize_utc_datetime(my_row.Bet.created_at),
            "outcome": my_outcome,
            "outcome_label": OUTCOME_LABELS[my_outcome],
            "quote": _build_detail_quote(
                match=match,
                choice=my_row.Bet.choice,
                outcome=my_outcome,
                stake=my_row.Bet.stake,
                points_earned=my_row.Bet.points_earned,
                winning_choice=winning_choice if result_published else None,
                name=_user_display_name(my_row.User),
            ),
            "reward_label": _format_reward_label(my_outcome, my_row.Bet.stake, my_row.Bet.points_earned),
        }

    settlement["headline_quote"] = _build_headline_quote(
        match=match,
        settlement=settlement,
        summary=summary,
    )

    return {
        "match": _match_response(match),
        "pool": {
            "total_pool": total_pool,
            "home_stakes": summary["HOME"]["stake"],
            "draw_stakes": summary["DRAW"]["stake"],
            "away_stakes": summary["AWAY"]["stake"],
            "home_count": summary["HOME"]["count"],
            "draw_count": summary["DRAW"]["count"],
            "away_count": summary["AWAY"]["count"],
        },
        "settlement": settlement,
        "bettors": bettors,
        "my_bet": my_bet,
    }

async def _build_profile_payload(
    user: User,
    db: Optional[AsyncSession] = None,
    *,
    include_badge: bool = True,
) -> dict:
    payload = {
        "id": str(user.id),
        "email": user.email,
        "display_name": _user_display_name(user),
        "profile_status": None,
        "total_points": user.total_points,
        "avatar_url": user.avatar_url,
        "avatar_color": user.avatar_color or "#6366f1",
        "initials": _user_initials(user),
        "is_admin": user.email.strip().lower() in ADMIN_EMAILS,
        "is_approved": bool(user.is_approved),
        "is_self": True,
        "can_edit": True,
    }
    if db is not None:
        payload["profile_status"] = await _get_latest_profile_status_content(db, user.id)
        payload["status_timeline"] = await _get_profile_status_timeline(db, user.id, viewer_user_id=user.id)
        payload["features"] = await _get_feature_settings(db)
        if include_badge:
            payload["badge"] = await _build_user_badge_for_profile(user, db)
    return payload
