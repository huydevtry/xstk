from fastapi import APIRouter

from app.schemas.payloads import (
    AdminSettingsPayload,
    AdminUserPointsPayload,
    BetPayload,
    MatchPayload,
    ProfileStatusPostPayload,
    ResolvePayload,
    UpdateProfilePayload,
)
from app.services.shared import (
    logger,
    templates,
    ASSET_VERSION,
    NO_CACHE_HEADERS,
    CHOICE_LABELS,
    OUTCOME_LABELS,
    MATCH_DEFAULT_DURATION,
    APP_TIMEZONE,
    MAX_PROFILE_NAME_LENGTH,
    MAX_TAUNT_LENGTH,
    MAX_PROFILE_STATUS_LENGTH,
    MAX_PROFILE_TIMELINE_ITEMS,
    DEFAULT_PROFILE_TIMELINE_PAGE_SIZE,
    MAX_PROFILE_TIMELINE_PAGE_SIZE,
    MAX_HOMEPAGE_ANNOUNCEMENT_LENGTH,
    PROFILE_POST_TYPE_TEXT,
    PROFILE_POST_TYPE_MATCH_REACTION,
    DEFAULT_POINT_TRANSACTION_PAGE_SIZE,
    MAX_POINT_TRANSACTION_PAGE_SIZE,
    POINT_TRANSACTIONS_BACKFILL_KEY,
    POINT_TRANSACTIONS_BACKFILL_VERSION,
    LOGOUT_URL,
    COUNTRY_CODE_PATH,
    COUNTRY_CODE_MAP,
    COUNTRY_CODE_OPTIONS,
    _utc_now_naive,
    _logout_url_for_request,
    _is_admin_viewer,
    _page_context,
    _serialize_utc_datetime,
    _serialize_app_datetime,
    _format_coins,
    _provided_fields,
    _normalize_display_name,
    _normalize_optional_taunt,
    _normalize_optional_profile_status,
    _normalize_timeline_limit,
    _normalize_point_transaction_limit,
    _serialize_profile_status_match,
    _serialize_match_reaction_result,
    _serialize_profile_status_post,
    _list_profile_status_posts,
    _get_profile_status_timeline,
    _create_profile_status_post,
    _has_match_reaction_post,
    _backfill_profile_status_timeline,
    _local_now_naive,
    _render_inline_markdown,
    render_markdown,
    DEFAULT_FEATURE_SETTINGS,
    _parse_bool_setting,
    _ensure_default_settings,
    _get_app_setting,
    _set_app_setting,
    _is_refund_backfill_case,
    _backfill_point_transactions,
    _get_feature_settings,
    _match_effective_end_time,
    _get_match_min_stake,
    _sync_match_statuses,
    _get_user_by_id,
    AVATARS_DIR,
    AVATAR_CONTENT_TYPES,
    _detect_image_content_type,
    _match_result_published,
    _match_response,
    _choice_label,
    _user_display_name,
    _user_initials,
    _user_avatar_payload,
    _point_transaction_type_label,
    _record_point_transaction,
    _serialize_point_transaction,
    _list_point_transactions,
    _get_match_reaction_match_ids,
    _serialize_bet_history_entry,
    _user_badge_payload,
    _build_user_badge_for_profile,
    _stable_pick,
    _format_reward_label,
    _build_detail_quote,
    _build_headline_quote,
    _build_match_detail_payload,
    _build_profile_payload,
    Depends,
    HTTPException,
    UploadFile,
    File,
    Query,
    HTMLResponse,
    RedirectResponse,
    Request,
    AsyncSession,
    select,
    func,
    case,
    desc,
    delete,
    update,
    IntegrityError,
    aliased,
    datetime,
    timedelta,
    timezone,
    Literal,
    Optional,
    logging,
    hashlib,
    random,
    uuid_lib,
    UUID,
    Path,
    Decimal,
    ROUND_DOWN,
    html,
    re,
    json,
    Base,
    get_db,
    Match,
    MatchStatus,
    Bet,
    User,
    ProfileStatusPost,
    PointTransaction,
    PointTransactionType,
    AppSetting,
    get_current_user,
    get_admin_user,
    get_request_user,
    ADMIN_EMAILS
)

router = APIRouter()

@router.get("/api/v1/leaderboard")
async def get_leaderboard(
    offset: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
):
    """Paginated leaderboard với badges tự động và trend indicator."""
    total_users = (
        await db.execute(
            select(func.count()).select_from(User).where(User.is_approved.is_(True))
        )
    ).scalar_one()

    users_q = (
        select(User)
        .where(User.is_approved.is_(True))
        .order_by(desc(User.total_points))
        .offset(offset)
        .limit(limit)
    )
    users = (await db.execute(users_q)).scalars().all()

    # Tính points_earned trong 24h gần nhất (trend)
    since = _utc_now_naive() - timedelta(hours=24)
    trend_q = (
        select(Bet.user_id, func.sum(Bet.points_earned).label("earned_24h"))
        .join(User, Bet.user_id == User.id)
        .where(Bet.created_at >= since, Bet.points_earned > 0)
        .where(User.is_approved.is_(True))
        .group_by(Bet.user_id)
    )
    trend_rows = (await db.execute(trend_q)).all()
    trend_map = {str(r.user_id): r.earned_24h for r in trend_rows}

    # Tính streak thua liên tiếp
    streak_q = (
        select(Bet.user_id, Bet.points_earned, Bet.created_at)
        .where(Bet.match_id.in_(
            select(Bet.match_id).where(
                Bet.match_id.in_(
                    select(Bet.match_id).scalar_subquery()
                )
            )
        ))
        .order_by(Bet.user_id, desc(Bet.created_at))
    )
    # Đơn giản hơn: lấy bets gần nhất của mỗi user
    all_bets_q = (
        select(Bet.user_id, Bet.points_earned, Bet.created_at)
        .join(User, Bet.user_id == User.id)
        .where(Bet.points_earned.is_not(None))
        .where(User.is_approved.is_(True))
        .order_by(Bet.user_id, desc(Bet.created_at))
    )
    all_bets = (await db.execute(all_bets_q)).all()

    # Group bets by user, tính streak
    from collections import defaultdict
    user_bets = defaultdict(list)
    for b in all_bets:
        user_bets[str(b.user_id)].append(b.points_earned)

    def calc_loss_streak(bets):
        streak = 0
        for earned in bets:
            if earned == 0:
                streak += 1
            else:
                break
        return streak

    # Kiểm tra "Nhà tiên tri": thắng khi chọn cửa thiểu số
    contrarian_q = (
        select(
            Bet.user_id,
            Bet.match_id,
            Bet.choice,
            Bet.points_earned,
        )
        .join(User, Bet.user_id == User.id)
        .where(Bet.points_earned > 0)
        .where(User.is_approved.is_(True))
    )
    contrarian_bets = (await db.execute(contrarian_q)).all()

    # Đếm số người đặt mỗi cửa của mỗi trận
    choice_count_q = (
        select(Bet.match_id, Bet.choice, func.count(Bet.id).label("cnt"))
        .join(User, Bet.user_id == User.id)
        .where(User.is_approved.is_(True))
        .group_by(Bet.match_id, Bet.choice)
    )
    choice_counts = (await db.execute(choice_count_q)).all()
    choice_map = {}  # (match_id, choice) -> count
    for cc in choice_counts:
        choice_map[(cc.match_id, cc.choice)] = cc.cnt

    contrarian_users = set()
    for cb in contrarian_bets:
        my_cnt = choice_map.get((cb.match_id, cb.choice), 1)
        all_cnts = [v for (mid, ch), v in choice_map.items() if mid == cb.match_id]
        if all_cnts and my_cnt == min(all_cnts) and my_cnt < max(all_cnts):
            contrarian_users.add(str(cb.user_id))

    leaderboard = []
    for idx, user in enumerate(users):
        rank = offset + idx + 1
        uid = str(user.id)
        streak_loss = calc_loss_streak(user_bets.get(uid, []))
        earned_24h = trend_map.get(uid, 0)
        trend = "up" if earned_24h > 0 else "down" if streak_loss > 0 else "neutral"
        is_contrarian = uid in contrarian_users

        # Badge logic
        if rank == 1:
            badge = {"label": "Đại gia", "emoji": "🤑", "color": "gold"}
        elif rank == total_users:
            badge = {"label": "Báo thủ", "emoji": "🐣", "color": "gray"}
        elif is_contrarian:
            badge = {"label": "Nhà tiên tri", "emoji": "🔮", "color": "purple"}
        elif streak_loss >= 3:
            badge = {"label": "Cứu rỗi", "emoji": "🙏", "color": "red"}
        else:
            badge = None

        leaderboard.append({
            "id": str(user.id),
            "rank": rank,
            "name": _user_display_name(user),
            "display_name": _user_display_name(user),
            "total_points": user.total_points,
            "avatar_url": user.avatar_url,
            "avatar_color": user.avatar_color or "#6366f1",
            "initials": _user_initials(user),
            "trend": trend,
            "earned_24h": earned_24h,
            "streak_loss": streak_loss,
            "badge": badge,
        })

    next_offset = offset + len(leaderboard)
    return {
        "items": leaderboard,
        "next_offset": next_offset if next_offset < total_users else None,
        "total": total_users,
    }
