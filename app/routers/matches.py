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

@router.get("/api/v1/matches")
async def get_upcoming_matches(db: AsyncSession = Depends(get_db)):
    await _sync_match_statuses(db)
    # Subquery: tổng stake theo (match_id, choice)
    pool_q = (
        select(
            Bet.match_id,
            func.sum(case((Bet.choice == "HOME", Bet.stake), else_=0)).label("stakes_home"),
            func.sum(case((Bet.choice == "DRAW", Bet.stake), else_=0)).label("stakes_draw"),
            func.sum(case((Bet.choice == "AWAY", Bet.stake), else_=0)).label("stakes_away"),
            func.sum(Bet.stake).label("total_pool"),
        )
        .join(User, Bet.user_id == User.id)
        .where(User.is_approved.is_(True))
        .group_by(Bet.match_id)
        .subquery()
    )
    min_stake_q = (
        select(
            Bet.match_id.label("match_id"),
            func.min(Bet.stake).label("min_stake"),
        )
        .join(User, Bet.user_id == User.id)
        .where(User.is_approved.is_(True))
        .group_by(Bet.match_id)
        .subquery()
    )

    query = (
        select(
            Match,
            func.coalesce(pool_q.c.stakes_home, 0).label("stakes_home"),
            func.coalesce(pool_q.c.stakes_draw, 0).label("stakes_draw"),
            func.coalesce(pool_q.c.stakes_away, 0).label("stakes_away"),
            func.coalesce(pool_q.c.total_pool, 0).label("total_pool"),
            min_stake_q.c.min_stake.label("min_stake"),
        )
        .outerjoin(pool_q, Match.id == pool_q.c.match_id)
        .outerjoin(min_stake_q, Match.id == min_stake_q.c.match_id)
        .where(Match.status != MatchStatus.finished)
        .order_by(case((Match.status == MatchStatus.live, 0), else_=1), Match.start_time.asc())
    )

    rows = (await db.execute(query)).all()

    return [
        {
            "id": r.Match.id,
            "home_team": r.Match.home_team,
            "home_icon": r.Match.home_icon,
            "away_team": r.Match.away_team,
            "away_icon": r.Match.away_icon,
            "home_score": r.Match.home_score,
            "away_score": r.Match.away_score,
            "home_penalty_score": getattr(r.Match, "home_penalty_score", None),
            "away_penalty_score": getattr(r.Match, "away_penalty_score", None),
            "handicap": r.Match.handicap,
            "status": r.Match.status,
            "start_time": _serialize_app_datetime(r.Match.start_time),
            "end_time": _serialize_app_datetime(_match_effective_end_time(r.Match)),
            "result_published": bool(r.Match.resolved_at),
            "stakes_home": r.stakes_home,
            "stakes_draw": r.stakes_draw,
            "stakes_away": r.stakes_away,
            "total_pool": r.total_pool,
            "min_stake": int(r.min_stake) if r.min_stake is not None else None,
        }
        for r in rows
    ]

@router.get("/api/v1/matches/schedule")
async def get_match_schedule(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _sync_match_statuses(db)
    rows = (
        await db.execute(
            select(Match).order_by(
                case(
                    (Match.status == MatchStatus.live, 0),
                    (Match.status == MatchStatus.upcoming, 1),
                    else_=2,
                ),
                Match.start_time.asc(),
                Match.id.asc(),
            )
        )
    ).scalars().all()
    return [_match_response(match) for match in rows]

@router.get("/api/v1/matches/{match_id}/bets-legacy")
async def get_match_bets(match_id: int, db: AsyncSession = Depends(get_db)):
    """Trả về danh sách người đặt cược mỗi cửa (HOME/DRAW/AWAY) cho avatar stack."""
    query = (
        select(Bet, User)
        .join(User, Bet.user_id == User.id)
        .where(Bet.match_id == match_id, User.is_approved.is_(True))
        .order_by(Bet.created_at.asc())
    )
    rows = (await db.execute(query)).all()

    result = {"HOME": [], "DRAW": [], "AWAY": []}
    choice_counts = {"HOME": 0, "DRAW": 0, "AWAY": 0}

    for r in rows:
        choice_counts[r.Bet.choice] = choice_counts.get(r.Bet.choice, 0) + 1

    for r in rows:
        name = _user_display_name(r.User)
        initials = _user_initials(r.User)
        # Lone wolf: chỉ có 1 người đặt cửa này, trong khi cửa khác có nhiều hơn
        my_count = choice_counts.get(r.Bet.choice, 0)
        other_max = max(v for k, v in choice_counts.items() if k != r.Bet.choice)
        is_lone_wolf = my_count == 1 and other_max >= 3

        entry = {
            **_user_avatar_payload(r.User),
            "stake": r.Bet.stake,
            "is_lone_wolf": is_lone_wolf,
        }
        result[r.Bet.choice].append(entry)

    return result

@router.get("/api/v1/matches/{match_id:int}/detail")
async def get_match_detail(
    match_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _sync_match_statuses(db)
    match = (await db.execute(
        select(Match).where(Match.id == match_id)
    )).scalars().first()
    if not match:
        raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")
    return await _build_match_detail_payload(match=match, user=user, db=db)

@router.get("/api/v1/matches/latest-finished/detail")
async def get_latest_finished_match_detail(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    matches = (
        await db.execute(
            select(Match)
            .where(Match.status == MatchStatus.finished)
            .order_by(desc(func.coalesce(Match.resolved_at, Match.start_time)), desc(Match.id))
            .limit(5)
        )
    ).scalars().all()
    if not matches:
        raise HTTPException(status_code=404, detail="Chưa có trận nào hoàn tất.")

    return [
        await _build_match_detail_payload(match=match, user=user, db=db)
        for match in matches
    ]

@router.get("/api/v1/activity-feed")
async def get_activity_feed(db: AsyncSession = Depends(get_db)):
    """20 hoạt động cược gần nhất để hiển thị trong Live Ticker."""
    query = (
        select(Bet, User, Match)
        .join(User, Bet.user_id == User.id)
        .join(Match, Bet.match_id == Match.id)
        .where(User.is_approved.is_(True))
        .order_by(desc(Bet.created_at))
        .limit(20)
    )
    rows = (await db.execute(query)).all()

    TEMPLATES = [
        "🔥 {name} vừa tất tay {stake} vào {team}",
        "💸 {name} đặt {stake} chọn {team}",
        "🎯 {name} tin tưởng {team} với {stake}",
        "🤡 {name} lại tiếp tục tin tưởng {team}",
        "😤 {name} quyết tâm với {team} — {stake}",
        "🃏 {name} bài ngửa {stake} vào {team}",
        "💰 {name} cược đậm {stake} vào {team}",
        "💪 {name} vô {stake} vào {team}, liệu có nhổ được xe?",
        "👍 {name} xuống xác {stake} vào {team}"
    ]

    CHOICE_LABELS = {"HOME": "Chủ nhà", "DRAW": "Hòa", "AWAY": "Khách"}

    activities = []
    for r in rows:
        name = _user_display_name(r.User)
        team = (
            r.Match.home_team if r.Bet.choice == "HOME"
            else r.Match.away_team if r.Bet.choice == "AWAY"
            else CHOICE_LABELS["DRAW"]
        )
        tpl = random.choice(TEMPLATES)
        # Dùng seed ổn định để template không đổi mỗi lần refresh
        seed = hash(f"{r.Bet.id}{r.Bet.created_at}")
        tpl = TEMPLATES[abs(seed) % len(TEMPLATES)]
        text = tpl.format(name=name, stake=_format_coins(r.Bet.stake), team=team)
        activities.append({
            "text": text,
            "time": _serialize_utc_datetime(r.Bet.created_at),
        })

    return activities

@router.get("/api/v1/matches/{match_id}/bets")
async def get_match_bets_v2(match_id: int, db: AsyncSession = Depends(get_db)):
    query = (
        select(Bet, User)
        .join(User, Bet.user_id == User.id)
        .where(Bet.match_id == match_id, User.is_approved.is_(True))
        .order_by(Bet.created_at.desc())
    )
    rows = (await db.execute(query)).all()

    result = {"HOME": [], "DRAW": [], "AWAY": []}
    choice_counts = {"HOME": 0, "DRAW": 0, "AWAY": 0}

    for row in rows:
        choice_counts[row.Bet.choice] = choice_counts.get(row.Bet.choice, 0) + 1

    for row in rows:
        my_count = choice_counts.get(row.Bet.choice, 0)
        other_max = max(v for k, v in choice_counts.items() if k != row.Bet.choice)
        is_lone_wolf = my_count == 1 and other_max >= 3
        result[row.Bet.choice].append(
            {
                **_user_avatar_payload(row.User),
                "stake": row.Bet.stake,
                "taunt_text": row.Bet.taunt_text,
                "created_at": _serialize_utc_datetime(row.Bet.created_at),
                "is_lone_wolf": is_lone_wolf,
            }
        )

    return result
