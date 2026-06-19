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
import asyncio
from uuid import UUID
from pathlib import Path
import csv
import io
from decimal import Decimal, ROUND_DOWN
import html
import re
import json

from app.database import engine, Base, get_db
from app.models import (
    Match,
    MatchStatus,
    Bet,
    User,
    ProfileStatusPost,
    PointRechargeRequest,
    PointRechargeStatus,
    PointTransaction,
    PointTransactionType,
    AppSetting,
)
from app.dependencies import get_current_user, get_admin_user, get_request_user, ADMIN_EMAILS
from app.notifications import notify_admin_recharge_request

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
    "PENDING": "Chờ kết quả",
}

MATCH_DEFAULT_DURATION = timedelta(hours=2)

APP_TIMEZONE = ZoneInfo("Asia/Ho_Chi_Minh")

MAX_PROFILE_NAME_LENGTH = 30

MAX_TAUNT_LENGTH = 30

MAX_PROFILE_STATUS_LENGTH = 160

MAX_PROFILE_TIMELINE_ITEMS = 20

DEFAULT_PROFILE_TIMELINE_PAGE_SIZE = 10

MAX_PROFILE_TIMELINE_PAGE_SIZE = 20

MAX_HOMEPAGE_ANNOUNCEMENT_LENGTH = 280

PROFILE_POST_TYPE_TEXT = "text"

PROFILE_POST_TYPE_MATCH_REACTION = "match_reaction"

DEFAULT_POINT_TRANSACTION_PAGE_SIZE = 20

MAX_POINT_TRANSACTION_PAGE_SIZE = 50

POINT_TRANSACTIONS_BACKFILL_KEY = "point_transactions_backfill_version"

POINT_TRANSACTIONS_BACKFILL_VERSION = "admin_seed_v2"

LOGOUT_URL = "https://learning.huydevtry.com/cdn-cgi/access/logout"

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

def _normalize_timeline_limit(limit: int) -> int:
    return max(1, min(limit, MAX_PROFILE_TIMELINE_PAGE_SIZE))

def _normalize_point_transaction_limit(limit: int) -> int:
    return max(1, min(limit, MAX_POINT_TRANSACTION_PAGE_SIZE))

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
    if bet.points_earned is None:
        return {
            "outcome": "refund",
            "outcome_label": "Hoàn điểm",
            "points_earned": None,
            "stake": bet.stake,
        }
    if int(bet.points_earned or 0) > 0:
        return {
            "outcome": "win",
            "outcome_label": "Thắng",
            "points_earned": bet.points_earned,
            "stake": bet.stake,
        }
    return {
        "outcome": "lose",
        "outcome_label": "Thua",
        "points_earned": 0,
        "stake": bet.stake,
    }

def _serialize_profile_status_post(
    post: ProfileStatusPost,
    *,
    author: Optional[User] = None,
    match: Optional[Match] = None,
    bet: Optional[Bet] = None,
) -> dict:
    return {
        "id": post.id,
        "post_type": (post.post_type or PROFILE_POST_TYPE_TEXT),
        "content": post.content,
        "created_at": _serialize_utc_datetime(post.created_at),
        "author": _user_avatar_payload(author) if author is not None else None,
        "match": _serialize_profile_status_match(match),
        "reaction_result": _serialize_match_reaction_result(bet=bet, match=match)
        if (post.post_type or PROFILE_POST_TYPE_TEXT) == PROFILE_POST_TYPE_MATCH_REACTION
        else None,
    }

async def _list_profile_status_posts(
    db: AsyncSession,
    *,
    user_id: Optional[UUID] = None,
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
    )
    if user_id is not None:
        query = query.where(ProfileStatusPost.user_id == user_id)
    query = (
        query
        .order_by(desc(ProfileStatusPost.created_at), desc(ProfileStatusPost.id))
        .offset(safe_offset)
        .limit(safe_limit + 1)
    )
    rows = (await db.execute(query)).all()
    page_rows = rows[:safe_limit]
    items = [
        _serialize_profile_status_post(
            row.ProfileStatusPost,
            author=row.User,
            match=row.Match,
            bet=row.Bet,
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
    limit: int = MAX_PROFILE_TIMELINE_ITEMS,
) -> list[dict]:
    page = await _list_profile_status_posts(
        db,
        user_id=user_id,
        offset=0,
        limit=min(limit, MAX_PROFILE_TIMELINE_ITEMS),
    )
    return page["items"]

async def _create_profile_status_post(
    db: AsyncSession,
    user: User,
    content: str,
    *,
    created_at: Optional[datetime] = None,
    post_type: str = PROFILE_POST_TYPE_TEXT,
    match: Optional[Match] = None,
) -> ProfileStatusPost:
    post = ProfileStatusPost(
        user_id=user.id,
        content=content,
        post_type=post_type,
        match_id=match.id if match is not None else None,
        created_at=created_at or _utc_now_naive(),
    )
    user.profile_status = content
    db.add(post)
    db.add(user)
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
    legacy_users = (
        await db.execute(
            select(User).where(User.profile_status.is_not(None))
        )
    ).scalars().all()
    if not legacy_users:
        return

    existing_user_ids = {
        user_id
        for user_id in (
            await db.execute(select(ProfileStatusPost.user_id).distinct())
        ).scalars().all()
        if user_id is not None
    }

    created = False
    for user in legacy_users:
        if user.id in existing_user_ids:
            continue
        content = _normalize_optional_profile_status(user.profile_status)
        if content is None:
            continue
        await _create_profile_status_post(
            db,
            user,
            content,
            created_at=user.created_at or _utc_now_naive(),
        )
        created = True

    if created:
        await db.commit()

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
    approved_recharges = (
        await db.execute(
            select(PointRechargeRequest)
            .where(PointRechargeRequest.status == PointRechargeStatus.approved)
            .order_by(PointRechargeRequest.approved_at.asc(), PointRechargeRequest.created_at.asc(), PointRechargeRequest.id.asc())
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
    recharge_by_user: dict[UUID, list[PointRechargeRequest]] = {}
    for request in approved_recharges:
        recharge_by_user.setdefault(request.user_id, []).append(request)
    bets_by_user: dict[UUID, list[Bet]] = {}
    for bet in bets:
        bets_by_user.setdefault(bet.user_id, []).append(bet)

    for user_id in bettor_ids:
        user = users.get(user_id)
        if user is None:
            continue

        events: list[dict] = []
        delta_sum = 0

        for request in recharge_by_user.get(user_id, []):
            created_at = request.approved_at or request.created_at or user.created_at or _utc_now_naive()
            delta = int(request.amount)
            delta_sum += delta
            events.append(
                {
                    "created_at": created_at,
                    "delta": delta,
                    "transaction_type": PointTransactionType.recharge_approved,
                    "description": f"Backfill: duyệt nạp điểm cũ #{request.id}",
                    "actor_user_id": request.approved_by_user_id,
                    "bet_id": None,
                    "match_id": None,
                    "recharge_request_id": request.id,
                }
            )

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
                    "recharge_request_id": None,
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
                        "recharge_request_id": None,
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
                        "recharge_request_id": None,
                    }
                )

        events.sort(key=lambda item: (item["created_at"], item["delta"] > 0, item["bet_id"] or 0, item["recharge_request_id"] or 0))
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
                    "recharge_request_id": None,
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
                    recharge_request_id=item["recharge_request_id"],
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

async def _match_status_sync_loop() -> None:
    while True:
        try:
            async with AsyncSession(engine) as session:
                await _sync_match_statuses(session)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to sync match statuses.")
        await asyncio.sleep(30)

async def _get_user_by_id(db: AsyncSession, user_id: str) -> User:
    try:
        parsed_id = uuid_lib.UUID(user_id)
    except ValueError:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại.")

    user = (await db.execute(select(User).where(User.id == parsed_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại.")
    return user

AVATARS_DIR = Path("static/avatars")

AVATAR_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
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

def _match_result_published(match: Match) -> bool:
    return match.status == MatchStatus.finished and bool(getattr(match, "resolved_at", None))

def _match_response(match: Match):
    return {
        "id": match.id,
        "home_team": match.home_team,
        "home_icon": match.home_icon,
        "away_team": match.away_team,
        "away_icon": match.away_icon,
        "home_score": match.home_score,
        "away_score": match.away_score,
        "handicap": match.handicap,
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
        PointTransactionType.recharge_approved: "Nạp điểm",
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
    recharge_request: Optional[PointRechargeRequest] = None,
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
        recharge_request_id=recharge_request.id if recharge_request is not None else None,
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
    recharge_request: Optional[PointRechargeRequest] = None,
) -> dict:
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
    recharge_payload = None
    if recharge_request is not None:
        recharge_payload = {
            "id": recharge_request.id,
            "amount": recharge_request.amount,
        }
    return {
        "id": transaction.id,
        "transaction_type": transaction.transaction_type,
        "transaction_type_label": _point_transaction_type_label(transaction.transaction_type),
        "delta_points": transaction.delta_points,
        "balance_after": transaction.balance_after,
        "description": transaction.description,
        "created_at": _serialize_utc_datetime(transaction.created_at),
        "is_backfilled": bool(transaction.is_backfilled),
        "actor": actor_payload,
        "bet": bet_payload,
        "match": match_payload,
        "recharge_request": recharge_payload,
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
            select(PointTransaction, actor_alias, Bet, Match, PointRechargeRequest)
            .outerjoin(actor_alias, PointTransaction.actor_user_id == actor_alias.id)
            .outerjoin(Bet, PointTransaction.bet_id == Bet.id)
            .outerjoin(Match, PointTransaction.match_id == Match.id)
            .outerjoin(PointRechargeRequest, PointTransaction.recharge_request_id == PointRechargeRequest.id)
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
            recharge_request=row.PointRechargeRequest,
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
) -> dict:
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
        "handicap": match.handicap,
        "start_time": _serialize_app_datetime(match.start_time),
        "choice": bet.choice,
        "stake": bet.stake,
        "points_earned": bet.points_earned,
        "created_at": _serialize_utc_datetime(bet.created_at),
        "result_published": _match_result_published(match),
        "can_share_reaction": can_share_reaction,
        "has_shared_reaction": has_shared_reaction,
    }

def _user_badge_payload(
    *,
    rank: Optional[int],
    total_users: int,
    streak_loss: int,
    is_contrarian: bool,
) -> Optional[dict]:
    if rank == 1:
        return {"label": "Đại gia", "emoji": "🤑", "color": "gold"}
    if rank == total_users:
        return {"label": "Báo thủ", "emoji": "🐣", "color": "gray"}
    if is_contrarian:
        return {"label": "Nhà tiên tri", "emoji": "🔮", "color": "purple"}
    if streak_loss >= 3:
        return {"label": "Cứu rỗi", "emoji": "🙏", "color": "red"}
    return None

async def _build_user_badge_for_profile(user: User, db: AsyncSession) -> Optional[dict]:
    ordered_ids = (
        await db.execute(
            select(User.id).order_by(desc(User.total_points), User.id.asc())
        )
    ).scalars().all()
    total_users = len(ordered_ids)
    if not total_users:
        return None

    rank = next((idx + 1 for idx, uid in enumerate(ordered_ids) if uid == user.id), None)
    if rank is None:
        return None

    since = _utc_now_naive() - timedelta(hours=24)
    trend_q = (
        select(func.sum(Bet.points_earned))
        .where(Bet.user_id == user.id, Bet.created_at >= since, Bet.points_earned > 0)
    )
    earned_24h = (await db.execute(trend_q)).scalar() or 0

    recent_bets = (
        await db.execute(
            select(Bet.points_earned)
            .where(Bet.user_id == user.id, Bet.points_earned.is_not(None))
            .order_by(Bet.created_at.desc())
        )
    ).scalars().all()

    streak_loss = 0
    for earned in recent_bets:
        if earned == 0:
            streak_loss += 1
        else:
            break

    winning_bets = (
        await db.execute(
            select(Bet.match_id, Bet.choice)
            .where(Bet.user_id == user.id, Bet.points_earned > 0)
        )
    ).all()
    is_contrarian = False
    for bet in winning_bets:
        counts = (
            await db.execute(
                select(Bet.choice, func.count(Bet.id).label("cnt"))
                .where(Bet.match_id == bet.match_id)
                .group_by(Bet.choice)
            )
        ).all()
        if not counts:
            continue
        counts_map = {row.choice: row.cnt for row in counts}
        my_cnt = counts_map.get(bet.choice, 0)
        all_cnts = list(counts_map.values())
        if all_cnts and my_cnt == min(all_cnts) and my_cnt < max(all_cnts):
            is_contrarian = True
            break

    return _user_badge_payload(
        rank=rank,
        total_users=total_users,
        streak_loss=streak_loss,
        is_contrarian=is_contrarian,
    )

def _recharge_request_response(request: PointRechargeRequest, user: Optional[User] = None, admin: Optional[User] = None) -> dict:
    payload = {
        "id": request.id,
        "amount": request.amount,
        "status": request.status,
        "created_at": _serialize_utc_datetime(request.created_at),
        "approved_at": _serialize_app_datetime(request.approved_at) if request.approved_at else None,
    }
    if user:
        payload["user"] = {
            "id": str(user.id),
            "email": user.email,
            **_user_avatar_payload(user),
            "total_points": user.total_points,
        }
    if admin:
        payload["approved_by"] = {
            "id": str(admin.id),
            "email": admin.email,
            "display_name": _user_display_name(admin),
        }
    return payload

def _stable_pick(options, seed: str) -> str:
    if not options:
        return ""
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return options[int(digest, 16) % len(options)]

def _format_reward_label(outcome: str, stake: int, points_earned: Optional[int]) -> str:
    if outcome == "WIN":
        return f"+{_format_coins(int(points_earned or 0))}"
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
        "LOSE": [
            "{name} chọn {choice} khá tự tin, nhưng kết quả lại trả lời theo kiểu rất thẳng.",
            "{name} vừa trải nghiệm một pha kèo không chiều lòng niềm tin.",
            "{name} đi cửa {choice} hơi sớm một nhịp. Hôm nay trực giác xin nghỉ phép.",
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
        .where(Bet.match_id == match.id)
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
    refunded = result_published and has_bets and (stakes_on_winner == 0)

    settlement = {
        "is_finished": is_finished,
        "result_published": result_published,
        "winning_choice": winning_choice if result_published else None,
        "winning_choice_label": _choice_label(winning_choice) if result_published else None,
        "adjusted_home_score": adjusted_home if result_published else None,
        "adjusted_away_score": adjusted_away if result_published else None,
        "adjusted_score": f"{adjusted_home}-{adjusted_away}" if result_published else None,
        "score": f"{match.home_score}-{match.away_score}" if result_published else None,
        "refunded": refunded,
        "winner_count": 0,
        "loser_count": 0,
        "refund_count": 0,
        "headline_quote": None,
    }

    for row in rows:
        if not result_published:
            outcome = "PENDING"
        elif refunded:
            outcome = "REFUND"
        elif row.Bet.choice == winning_choice:
            outcome = "WIN"
        else:
            outcome = "LOSE"

        if outcome == "WIN":
            settlement["winner_count"] += 1
        elif outcome == "LOSE":
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
        if not result_published:
            my_outcome = "PENDING"
        elif refunded:
            my_outcome = "REFUND"
        elif my_row.Bet.choice == winning_choice:
            my_outcome = "WIN"
        else:
            my_outcome = "LOSE"

        my_bet = {
            "choice": my_row.Bet.choice,
            "stake": my_row.Bet.stake,
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

def _clean_csv_value(row: dict, key: str, default: str = "") -> str:
    value = row.get(key, default)
    if value is None:
        return default
    return str(value).strip()

def _csv_field_provided(row: dict, key: str) -> bool:
    return key in row and row.get(key) is not None and str(row.get(key)).strip() != ""

def _parse_csv_datetime(value: str) -> datetime:
    value = value.strip()
    if not value:
        raise ValueError("start_time is required")
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    raise ValueError("Invalid start_time format")

def _parse_optional_int(value: str, default: int = 0) -> int:
    if value == "":
        return default
    return int(float(value))

def _parse_optional_float(value: str, default: float = 0.0) -> float:
    if value == "":
        return default
    return float(value)

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
        "default_taunt": user.default_taunt,
        "profile_status": user.profile_status,
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
        payload["status_timeline"] = await _get_profile_status_timeline(db, user.id)
        if payload["status_timeline"]:
            payload["profile_status"] = payload["status_timeline"][0]["content"]
        payload["features"] = await _get_feature_settings(db)
        if include_badge:
            payload["badge"] = await _build_user_badge_for_profile(user, db)
    return payload
