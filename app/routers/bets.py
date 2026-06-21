from fastapi import APIRouter

from app.schemas.payloads import (
    AdminSettingsPayload,
    AdminUserPointsPayload,
    BetPayload,
    BetTauntPayload,
    MatchPayload,
    ProfileStatusPostPayload,
    ResolvePayload,
    UpdateBetPayload,
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

@router.post("/api/v1/bets-legacy", status_code=201)
async def place_bet(
    payload: BetPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _sync_match_statuses(db)
    # Validate match
    match = (await db.execute(
        select(Match).where(Match.id == payload.match_id)
    )).scalars().first()

    if not match:
        raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")
    if match.status != MatchStatus.upcoming:
        raise HTTPException(status_code=400, detail="Trận này đã lên thớt.")

    min_stake = await _get_match_min_stake(db, payload.match_id)
    if min_stake is not None and payload.stake < min_stake:
        raise HTTPException(
            status_code=400,
            detail=f"Số điểm tối thiểu cho trận này là {_format_coins(min_stake)}.",
        )

    # Validate balance
    if user.total_points < payload.stake:
        raise HTTPException(status_code=400, detail="Số điểm không đủ.")

    # Kiểm tra đã cược chưa (1 user / 1 match)
    existing = (await db.execute(
        select(Bet).where(Bet.user_id == user.id, Bet.match_id == payload.match_id)
    )).scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail="Lệnh xuống xác đã được ghi nhận. Không được quay xe!")

    try:
        balance_update = await db.execute(
            update(User)
            .where(User.id == user.id, User.total_points >= payload.stake)
            .values(total_points=User.total_points - payload.stake)
            .execution_options(synchronize_session=False)
        )
        if balance_update.rowcount != 1:
            await db.rollback()
            raise HTTPException(status_code=400, detail="Số điểm không đủ.")

        bet = Bet(
            user_id=user.id,
            match_id=payload.match_id,
            choice=payload.choice,
            stake=payload.stake,
            points_earned=None,
        )
        db.add(bet)
        await db.flush()
        user.total_points -= payload.stake
        await _record_point_transaction(
            db,
            user=user,
            delta_points=-payload.stake,
            transaction_type=PointTransactionType.bet_stake,
            description=f"Đặt cược: {match.home_team} vs {match.away_team}",
            bet=bet,
            match=match,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Lệnh xuống xác đã được ghi nhận!")
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    await db.refresh(user)
    return {"message": "Chốt đơn thành công! Bắt đầu gáy thôi!", "remaining_points": user.total_points, "min_stake": min_stake}

@router.post("/api/v1/bets", status_code=201)
async def place_bet_v2(
    payload: BetPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _sync_match_statuses(db)

    match = (
        await db.execute(select(Match).where(Match.id == payload.match_id))
    ).scalars().first()
    if not match:
        raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")
    if match.status != MatchStatus.upcoming:
        raise HTTPException(status_code=400, detail="Trận này đã khóa đặt cược.")

    # Kèo chấp lẻ (0.5, 1.5, ...) không có kết quả hòa
    if payload.choice == "DRAW" and match.handicap % 1 != 0:
        raise HTTPException(status_code=400, detail="Kèo chấp lẻ không có cửa hòa.")

    min_stake = await _get_match_min_stake(db, payload.match_id)
    if min_stake is not None and payload.stake < min_stake:
        raise HTTPException(
            status_code=400,
            detail=f"Số điểm tối thiểu cho trận này là {_format_coins(min_stake)}.",
        )
    if user.total_points < payload.stake:
        raise HTTPException(status_code=400, detail="Số điểm không đủ.")

    taunt_text = _normalize_optional_taunt(payload.taunt_text)

    existing = (
        await db.execute(
            select(Bet).where(Bet.user_id == user.id, Bet.match_id == payload.match_id)
        )
    ).scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail="Bạn đã đặt cược trận này rồi.")

    try:
        balance_update = await db.execute(
            update(User)
            .where(User.id == user.id, User.total_points >= payload.stake)
            .values(total_points=User.total_points - payload.stake)
            .execution_options(synchronize_session=False)
        )
        if balance_update.rowcount != 1:
            await db.rollback()
            raise HTTPException(status_code=400, detail="Số điểm không đủ.")

        bet = Bet(
            user_id=user.id,
            match_id=payload.match_id,
            choice=payload.choice,
            stake=payload.stake,
            taunt_text=taunt_text,
            points_earned=None,
        )
        db.add(bet)
        await db.flush()
        user.total_points -= payload.stake
        await _record_point_transaction(
            db,
            user=user,
            delta_points=-payload.stake,
            transaction_type=PointTransactionType.bet_stake,
            description=f"Đặt cược: {match.home_team} vs {match.away_team}",
            bet=bet,
            match=match,
        )
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Bạn đã đặt cược trận này rồi.")
    except HTTPException:
        raise
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))

    await db.refresh(user)
    return {
        "message": "Đặt cược thành công.",
        "bet_id": bet.id,
        "match_id": match.id,
        "choice": bet.choice,
        "stake": bet.stake,
        "remaining_points": user.total_points,
        "min_stake": min_stake,
        "taunt_text": taunt_text,
    }

@router.patch("/api/v1/bets/{match_id}")
async def update_bet(
    match_id: int,
    payload: UpdateBetPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _sync_match_statuses(db)

    match = (
        await db.execute(select(Match).where(Match.id == match_id))
    ).scalars().first()
    if not match:
        raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")
    if match.status != MatchStatus.upcoming:
        raise HTTPException(status_code=400, detail="Trận này đã bắt đầu, không thể sửa cược.")

    # Kèo chấp lẻ không có cửa hòa, kể cả khi user đang sửa cược.
    if payload.choice == "DRAW" and match.handicap % 1 != 0:
        raise HTTPException(status_code=400, detail="Kèo chấp lẻ không có cửa hòa.")

    bet = (
        await db.execute(
            select(Bet).where(Bet.user_id == user.id, Bet.match_id == match_id)
        )
    ).scalars().first()
    if not bet:
        raise HTTPException(status_code=404, detail="Bạn chưa đặt cược trận này.")

    bet.choice = payload.choice
    bet.taunt_text = _normalize_optional_taunt(payload.taunt_text)
    db.add(bet)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "message": "Đã cập nhật cược.",
        "bet_id": bet.id,
        "match_id": bet.match_id,
        "choice": bet.choice,
        "stake": bet.stake,
        "taunt_text": bet.taunt_text,
    }

@router.patch("/api/v1/bets/{match_id}/taunt")
async def update_bet_taunt(
    match_id: int,
    payload: BetTauntPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _sync_match_statuses(db)

    match = (
        await db.execute(select(Match).where(Match.id == match_id))
    ).scalars().first()
    if not match:
        raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")
    if match.status != MatchStatus.upcoming:
        raise HTTPException(status_code=400, detail="Trận này đã khóa sửa câu gáy.")

    bet = (
        await db.execute(
            select(Bet).where(Bet.user_id == user.id, Bet.match_id == match_id)
        )
    ).scalars().first()
    if not bet:
        raise HTTPException(status_code=404, detail="Bạn chưa đặt cược trận này.")

    bet.taunt_text = _normalize_optional_taunt(payload.taunt_text)
    db.add(bet)

    try:
        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))

    return {
        "message": "Đã cập nhật câu gáy.",
        "bet_id": bet.id,
        "match_id": bet.match_id,
        "choice": bet.choice,
        "stake": bet.stake,
        "taunt_text": bet.taunt_text,
    }
