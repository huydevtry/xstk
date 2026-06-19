from fastapi import APIRouter

from app.schemas.payloads import (
    AdminSettingsPayload,
    AdminUserPointsPayload,
    BetPayload,
    MatchPayload,
    PointRechargePayload,
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
    _match_status_sync_loop,
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
    _recharge_request_response,
    _stable_pick,
    _format_reward_label,
    _build_detail_quote,
    _build_headline_quote,
    _build_match_detail_payload,
    _clean_csv_value,
    _csv_field_provided,
    _parse_csv_datetime,
    _parse_optional_int,
    _parse_optional_float,
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
    asyncio,
    UUID,
    Path,
    csv,
    io,
    Decimal,
    ROUND_DOWN,
    html,
    re,
    json,
    engine,
    Base,
    get_db,
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
    get_current_user,
    get_admin_user,
    get_request_user,
    ADMIN_EMAILS,
    notify_admin_recharge_request
)

router = APIRouter()

@router.get("/api/v1/admin/users/{user_id}/point-transactions")
async def get_admin_user_point_transactions(
    user_id: UUID,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_POINT_TRANSACTION_PAGE_SIZE, ge=1, le=MAX_POINT_TRANSACTION_PAGE_SIZE),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại.")
    return await _list_point_transactions(db, user_id=user.id, offset=offset, limit=limit)

@router.get("/api/v1/admin/overview")
async def get_admin_overview(admin_user: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    await _sync_match_statuses(db)
    total_users = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    total_matches = (await db.execute(select(func.count()).select_from(Match))).scalar_one()
    upcoming_matches = (
        await db.execute(select(func.count()).select_from(Match).where(Match.status == MatchStatus.upcoming))
    ).scalar_one()
    total_bets = (await db.execute(select(func.count()).select_from(Bet))).scalar_one()
    wallet_points = (await db.execute(select(func.coalesce(func.sum(User.total_points), 0)))).scalar_one()
    locked_points = (
        await db.execute(
            select(func.coalesce(func.sum(Bet.stake), 0))
            .join(Match, Match.id == Bet.match_id)
            .where(Match.resolved_at.is_(None))
        )
    ).scalar_one()
    total_points = int(wallet_points or 0) + int(locked_points or 0)
    feature_settings = await _get_feature_settings(db)

    return {
        "total_users": total_users,
        "total_matches": total_matches,
        "upcoming_matches": upcoming_matches,
        "total_bets": total_bets,
        "total_points": total_points,
        "wallet_points": int(wallet_points or 0),
        "locked_points": int(locked_points or 0),
        "features": feature_settings,
    }

@router.get("/api/v1/admin/settings")
async def get_admin_settings(admin_user: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    return await _get_feature_settings(db)

@router.post("/api/v1/admin/settings")
async def update_admin_settings(
    payload: AdminSettingsPayload,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    await _ensure_default_settings(db)
    settings = (await db.execute(select(AppSetting))).scalars().all()
    settings_map = {item.key: item for item in settings}
    provided_fields = _provided_fields(payload)
    values_to_update: dict[str, bool | str] = {
        "points_enabled": payload.points_enabled,
    }
    if "homepage_announcement" in provided_fields:
        values_to_update["homepage_announcement"] = payload.homepage_announcement.strip()

    for key, value in values_to_update.items():
        setting = settings_map.get(key)
        if not setting:
            if isinstance(value, bool):
                setting = AppSetting(key=key, value="1" if value else "0")
            else:
                setting = AppSetting(key=key, value=value)
        else:
            if isinstance(value, bool):
                setting.value = "1" if value else "0"
            else:
                setting.value = value
        db.add(setting)

    await db.commit()
    return await _get_feature_settings(db)

@router.get("/api/v1/admin/users")
async def get_admin_users(
    q: str = "",
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    users = (
        await db.execute(
            select(User).order_by(
                case((User.is_approved.is_(False), 0), else_=1),
                desc(User.created_at),
            )
        )
    ).scalars().all()
    bets = (await db.execute(select(Bet).order_by(desc(Bet.created_at)))).scalars().all()

    search = q.strip().lower()
    filtered_users = [
        user for user in users
        if not search
        or search in user.email.lower()
        or search in (user.display_name or "").lower()
    ]

    bets_by_user: dict[str, list[Bet]] = {}
    for bet in bets:
        bets_by_user.setdefault(str(bet.user_id), []).append(bet)

    return [
        {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
            "total_points": user.total_points,
            "is_approved": bool(user.is_approved),
            "approved_at": _serialize_utc_datetime(user.approved_at),
            "created_at": _serialize_utc_datetime(user.created_at),
            "last_bet_at": _serialize_utc_datetime(bets_by_user[str(user.id)][0].created_at) if bets_by_user.get(str(user.id)) else None,
            "bet_count": len(bets_by_user.get(str(user.id), [])),
            "win_count": sum(
                1
                for bet in bets_by_user.get(str(user.id), [])
                if (bet.points_earned or 0) > 0
            ),
            "loss_count": sum(
                1
                for bet in bets_by_user.get(str(user.id), [])
                if bet.points_earned == 0
            ),
            "is_admin": user.email.strip().lower() in ADMIN_EMAILS,
        }
        for user in filtered_users
    ]

@router.post("/api/v1/admin/users/{user_id}/approve")
async def approve_admin_user(
    user_id: UUID,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại.")

    if not user.is_approved:
        user.is_approved = True
        user.approved_at = _utc_now_naive()
        user.approved_by_user_id = admin_user.id
        db.add(user)
        await db.commit()
        await db.refresh(user)

    return {
        "id": str(user.id),
        "is_approved": bool(user.is_approved),
        "approved_at": _serialize_utc_datetime(user.approved_at),
    }

@router.post("/api/v1/admin/users/{user_id}/points")
async def update_admin_user_points(
    user_id: UUID,
    payload: AdminUserPointsPayload,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    user = (await db.execute(select(User).where(User.id == user_id))).scalars().first()
    if not user:
        raise HTTPException(status_code=404, detail="Người dùng không tồn tại.")

    reason = payload.reason.strip()
    if not reason:
        raise HTTPException(status_code=400, detail="Vui lòng nhập lý do điều chỉnh điểm.")

    delta = int(payload.total_points) - int(user.total_points or 0)
    user.total_points = payload.total_points
    db.add(user)
    transaction = None
    if delta != 0:
        transaction = await _record_point_transaction(
            db,
            user=user,
            delta_points=delta,
            transaction_type=PointTransactionType.admin_adjustment,
            description=reason,
            actor=admin_user,
        )
    await db.commit()
    await db.refresh(user)
    if transaction is not None:
        await db.refresh(transaction)

    return {
        "id": str(user.id),
        "total_points": user.total_points,
        "transaction": _serialize_point_transaction(transaction, actor=admin_user) if transaction is not None else None,
    }

@router.get("/api/v1/admin/matches")
async def get_all_matches(admin_user: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    await _sync_match_statuses(db)
    query = select(Match).order_by(Match.start_time.asc())
    rows = (await db.execute(query)).scalars().all()
    return [_match_response(r) for r in rows]

@router.get("/api/v1/admin/recharge-requests")
async def get_recharge_requests(admin_user: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    rows = (
        await db.execute(
            select(PointRechargeRequest, User)
            .join(User, PointRechargeRequest.user_id == User.id)
            .order_by(
                case((PointRechargeRequest.status == PointRechargeStatus.pending, 0), else_=1),
                PointRechargeRequest.created_at.desc(),
            )
        )
    ).all()
    return [_recharge_request_response(request, user) for request, user in rows]

@router.post("/api/v1/admin/recharge-requests/{request_id}/approve")
async def approve_recharge_request(
    request_id: int,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    request = (
        await db.execute(select(PointRechargeRequest).where(PointRechargeRequest.id == request_id))
    ).scalars().first()
    if not request:
        raise HTTPException(status_code=404, detail="Yêu cầu nạp điểm không tồn tại.")
    if request.status != PointRechargeStatus.pending:
        raise HTTPException(status_code=409, detail="Yêu cầu này đã được xử lý.")

    try:
        approved_at = _local_now_naive()
        status_update = await db.execute(
            update(PointRechargeRequest)
            .where(
                PointRechargeRequest.id == request_id,
                PointRechargeRequest.status == PointRechargeStatus.pending,
            )
            .values(
                status=PointRechargeStatus.approved,
                approved_at=approved_at,
                approved_by_user_id=admin_user.id,
            )
            .execution_options(synchronize_session=False)
        )
        if status_update.rowcount != 1:
            await db.rollback()
            raise HTTPException(status_code=409, detail="Yêu cầu này đã được xử lý.")

        await db.execute(
            update(User)
            .where(User.id == request.user_id)
            .values(total_points=User.total_points + request.amount)
            .execution_options(synchronize_session=False)
        )
        user = (
            await db.execute(select(User).where(User.id == request.user_id))
        ).scalars().first()
        if user:
            await _record_point_transaction(
                db,
                user=user,
                delta_points=request.amount,
                transaction_type=PointTransactionType.recharge_approved,
                description=f"Admin duyệt nạp điểm #{request.id}",
                actor=admin_user,
                recharge_request=request,
            )
        await db.commit()
        await db.refresh(request)
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    user = (
        await db.execute(select(User).where(User.id == request.user_id))
    ).scalars().first()
    if user:
        await db.refresh(user)
    return {
        "message": "Đã xác nhận và cộng điểm cho user.",
        "request": _recharge_request_response(request, user, admin_user),
    }

@router.post("/api/v1/admin/matches", status_code=201)
async def create_match(
    payload: MatchPayload,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.status == MatchStatus.finished:
        raise HTTPException(status_code=400, detail="Hãy dùng chức năng giải trận để kết thúc trận.")
    end_time = payload.end_time or (payload.start_time + MATCH_DEFAULT_DURATION)
    if end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="Giờ kết thúc phải sau giờ bắt đầu.")

    try:
        match = Match(
            home_team=payload.home_team.strip(),
            home_icon=(payload.home_icon or "").strip() or None,
            away_team=payload.away_team.strip(),
            away_icon=(payload.away_icon or "").strip() or None,
            handicap=payload.handicap,
            status=payload.status,
            start_time=payload.start_time,
            end_time=end_time,
        )
        db.add(match)
        await db.commit()
        await db.refresh(match)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": "Đã thêm trận đấu.", "match": _match_response(match)}

@router.post("/api/v1/admin/matches/import-csv")
async def import_matches_csv(
    file: UploadFile = File(...),
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    filename = (file.filename or "").lower()
    if not filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận file CSV.")

    contents = await file.read()
    if len(contents) > 2 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File CSV tối đa 2MB.")

    try:
        text = contents.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="File CSV cần dùng mã hóa UTF-8.")

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="File CSV không có header.")

    imported = 0
    created = 0
    updated = 0
    errors = []

    try:
        fieldnames = set(reader.fieldnames or [])
        for line_no, row in enumerate(reader, start=2):
            if not any(str(v or "").strip() for v in row.values()):
                continue

            try:
                raw_id = _clean_csv_value(row, "id")
                match = None
                if raw_id:
                    match = (
                        await db.execute(select(Match).where(Match.id == int(raw_id)))
                    ).scalars().first()

                home_team_provided = _csv_field_provided(row, "home_team")
                away_team_provided = _csv_field_provided(row, "away_team")
                home_team = _clean_csv_value(row, "home_team") if home_team_provided else (match.home_team if match else "")
                away_team = _clean_csv_value(row, "away_team") if away_team_provided else (match.away_team if match else "")
                if not home_team or not away_team:
                    raise ValueError("home_team and away_team are required")

                status_provided = _csv_field_provided(row, "status")
                status_value = (
                    _clean_csv_value(row, "status")
                    if status_provided
                    else (match.status.value if match else MatchStatus.upcoming.value)
                ) or MatchStatus.upcoming.value
                status = MatchStatus(status_value)
                if status == MatchStatus.finished:
                    raise ValueError("Use resolve match flow instead of importing finished status")

                start_time_raw = _clean_csv_value(row, "start_time") or _clean_csv_value(row, "start_time_ict")
                if start_time_raw:
                    start_time = _parse_csv_datetime(start_time_raw)
                elif match:
                    start_time = match.start_time
                else:
                    raise ValueError("start_time is required")

                end_time_provided = _csv_field_provided(row, "end_time")
                end_time_value = _clean_csv_value(row, "end_time")
                if end_time_provided:
                    end_time = _parse_csv_datetime(end_time_value)
                elif match and match.end_time:
                    end_time = match.end_time
                else:
                    end_time = start_time + MATCH_DEFAULT_DURATION
                if end_time <= start_time:
                    raise ValueError("end_time must be after start_time")

                home_score = (
                    _parse_optional_int(_clean_csv_value(row, "home_score"), 0)
                    if _csv_field_provided(row, "home_score")
                    else (match.home_score if match else 0)
                )
                away_score = (
                    _parse_optional_int(_clean_csv_value(row, "away_score"), 0)
                    if _csv_field_provided(row, "away_score")
                    else (match.away_score if match else 0)
                )
                handicap = (
                    _parse_optional_float(_clean_csv_value(row, "handicap"), 0.0)
                    if _csv_field_provided(row, "handicap")
                    else (match.handicap if match else 0.0)
                )
                home_icon = (
                    _clean_csv_value(row, "home_icon") or None
                    if "home_icon" in fieldnames and row.get("home_icon") is not None
                    else (match.home_icon if match else None)
                )
                away_icon = (
                    _clean_csv_value(row, "away_icon") or None
                    if "away_icon" in fieldnames and row.get("away_icon") is not None
                    else (match.away_icon if match else None)
                )

                if match:
                    match.home_team = home_team
                    match.away_team = away_team
                    match.home_icon = home_icon
                    match.away_icon = away_icon
                    match.home_score = home_score
                    match.away_score = away_score
                    match.handicap = handicap
                    match.status = status
                    match.start_time = start_time
                    match.end_time = end_time
                    updated += 1
                else:
                    match_kwargs = {
                        "home_team": home_team,
                        "away_team": away_team,
                        "home_icon": home_icon,
                        "away_icon": away_icon,
                        "home_score": home_score,
                        "away_score": away_score,
                        "handicap": handicap,
                        "status": status,
                        "start_time": start_time,
                        "end_time": end_time,
                    }
                    if raw_id:
                        match_kwargs["id"] = int(raw_id)
                    match = Match(**match_kwargs)
                    created += 1

                db.add(match)
                imported += 1
            except Exception as e:
                errors.append({"line": line_no, "error": str(e)})
                if len(errors) >= 10:
                    break

        if errors:
            await db.rollback()
            return {
                "message": "Import thất bại. Chưa có trận nào được lưu.",
                "imported": 0,
                "created": 0,
                "updated": 0,
                "errors": errors,
            }

        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "message": f"Đã import {imported} trận đấu.",
        "imported": imported,
        "created": created,
        "updated": updated,
        "errors": [],
    }

@router.post("/api/v1/admin/matches/{match_id}/update")
async def update_match(
    match_id: int,
    payload: MatchPayload,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    match = (await db.execute(select(Match).where(Match.id == match_id))).scalars().first()
    if not match:
        raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")
    if match.status == MatchStatus.finished:
        raise HTTPException(status_code=400, detail="Không thể sửa trận đã giải.")
    if payload.status == MatchStatus.finished:
        raise HTTPException(status_code=400, detail="Hãy dùng chức năng giải trận để kết thúc trận.")
    end_time = payload.end_time or (payload.start_time + MATCH_DEFAULT_DURATION)
    if end_time <= payload.start_time:
        raise HTTPException(status_code=400, detail="Giờ kết thúc phải sau giờ bắt đầu.")

    try:
        match.home_team = payload.home_team.strip()
        match.home_icon = (payload.home_icon or "").strip() or None
        match.away_team = payload.away_team.strip()
        match.away_icon = (payload.away_icon or "").strip() or None
        match.handicap = payload.handicap
        match.status = payload.status
        match.start_time = payload.start_time
        match.end_time = end_time
        db.add(match)
        await db.commit()
        await db.refresh(match)
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": "Đã cập nhật trận đấu.", "match": _match_response(match)}

@router.post("/api/v1/admin/matches/{match_id}/delete")
async def delete_match(
    match_id: int,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    match = (await db.execute(select(Match).where(Match.id == match_id))).scalars().first()
    if not match:
        raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")

    bet_count = (await db.execute(
        select(func.count(Bet.id)).where(Bet.match_id == match_id)
    )).scalar_one()
    if bet_count:
        raise HTTPException(status_code=400, detail="Không thể xóa trận đã có người đặt cược.")

    try:
        await db.delete(match)
        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": "Đã xóa trận đấu."}

@router.post("/api/v1/admin/resolve-match/{match_id}")
async def resolve_match(
    match_id: int,
    payload: ResolvePayload,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    await _sync_match_statuses(db)
    match = (await db.execute(
        select(Match).where(Match.id == match_id)
    )).scalars().first()

    if not match:
        raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")
    if match.status != MatchStatus.finished:
        raise HTTPException(status_code=400, detail="Trận chưa kết thúc, chưa thể giải.")
    if match.resolved_at is not None:
        raise HTTPException(status_code=400, detail="Trận đã được giải trước đó.")

    try:
        # Lưu score
        match.home_score = payload.home_score
        match.away_score = payload.away_score

        # Tính adjusted score với handicap
        adjusted_home = payload.home_score + match.handicap
        adjusted_away = payload.away_score

        if adjusted_home > adjusted_away:
            winning_choice = "HOME"
        elif adjusted_home < adjusted_away:
            winning_choice = "AWAY"
        else:
            winning_choice = "DRAW"

        # Lấy tất cả bets của trận
        bets = (await db.execute(
            select(Bet).where(Bet.match_id == match_id)
        )).scalars().all()
        user_ids = list({bet.user_id for bet in bets})
        users_by_id = {
            item.id: item
            for item in (
                await db.execute(select(User).where(User.id.in_(user_ids)))
            ).scalars().all()
        } if user_ids else {}

        total_pool = sum(b.stake for b in bets)
        winning_bets = [b for b in bets if b.choice == winning_choice]
        stakes_on_winner = sum(b.stake for b in winning_bets)
        refunded = not winning_bets or stakes_on_winner == 0

        if refunded:
            # Refund tất cả nếu không có ai cược đúng
            for bet in bets:
                bet.points_earned = None
                db.add(bet)
                user_q = users_by_id.get(bet.user_id)
                if user_q:
                    user_q.total_points += bet.stake
                    db.add(user_q)
                    await _record_point_transaction(
                        db,
                        user=user_q,
                        delta_points=bet.stake,
                        transaction_type=PointTransactionType.bet_refund,
                        description=f"Hoàn điểm trận: {match.home_team} vs {match.away_team}",
                        bet=bet,
                        match=match,
                    )
        else:
            for bet in bets:
                bet.points_earned = 0
                db.add(bet)

            allocations = []
            total_allocated = 0
            pool_decimal = Decimal(total_pool)
            winner_decimal = Decimal(stakes_on_winner)

            for bet in winning_bets:
                exact_reward = (pool_decimal * Decimal(bet.stake)) / winner_decimal
                reward = int(exact_reward.to_integral_value(rounding=ROUND_DOWN))
                allocations.append((bet, reward, exact_reward - Decimal(reward)))
                total_allocated += reward

            remainder = total_pool - total_allocated
            allocations.sort(key=lambda item: (-item[2], item[0].created_at, item[0].id))

            for index, (bet, reward, _) in enumerate(allocations):
                final_reward = reward + (1 if index < remainder else 0)
                bet.points_earned = final_reward
                db.add(bet)

                user_q = users_by_id.get(bet.user_id)
                if user_q:
                    user_q.total_points += final_reward
                    db.add(user_q)
                    await _record_point_transaction(
                        db,
                        user=user_q,
                        delta_points=final_reward,
                        transaction_type=PointTransactionType.bet_reward,
                        description=f"Thưởng cược trận: {match.home_team} vs {match.away_team}",
                        bet=bet,
                        match=match,
                    )

        match.status = MatchStatus.finished
        match.resolved_at = _local_now_naive()
        db.add(match)
        await db.commit()

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "message": f"Đã giải trận. Kết quả kèo: {winning_choice}.",
        "adjusted_score": f"{adjusted_home} - {adjusted_away}",
        "winning_choice": winning_choice,
        "total_pool": total_pool,
        "refunded": refunded,
    }

