from fastapi import APIRouter
from app.services import push_service

from app.schemas.payloads import (
    AdminBroadcastNotificationPayload,
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
    _compute_two_way_settlement,
    _resolve_market_winning_choice,
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

@router.post("/api/v1/admin/notifications/broadcast")
async def broadcast_admin_notification(
    payload: AdminBroadcastNotificationPayload,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    title = payload.title.strip()
    body = payload.body.strip()
    url = (payload.url or "/").strip() or "/"
    if not title or not body:
        raise HTTPException(status_code=400, detail="Vui lòng nhập tiêu đề và nội dung thông báo.")
    if not (url.startswith("/") or url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="URL thông báo phải bắt đầu bằng /, http:// hoặc https://.")

    users = (
        await db.execute(select(User).where(User.is_approved.is_(True)).order_by(User.created_at.asc()))
    ).scalars().all()

    for user in users:
        await push_service.enqueue_web_push(
            db,
            user_id=user.id,
            title=title,
            body=body,
            url=url,
            commit=False,
        )
    await db.commit()

    return {
        "message": f"Đã đưa thông báo vào hàng đợi cho {len(users)} người dùng.",
        "recipient_count": len(users),
    }

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
    round_label = (payload.round_label or "").strip() or None

    try:
        match = Match(
            home_team=payload.home_team.strip(),
            home_icon=(payload.home_icon or "").strip() or None,
            away_team=payload.away_team.strip(),
            away_icon=(payload.away_icon or "").strip() or None,
            handicap=payload.handicap,
            round_label=round_label,
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
    round_label = (payload.round_label or "").strip() or None

    try:
        match.home_team = payload.home_team.strip()
        match.home_icon = (payload.home_icon or "").strip() or None
        match.away_team = payload.away_team.strip()
        match.away_icon = (payload.away_icon or "").strip() or None
        match.handicap = payload.handicap
        match.round_label = round_label
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

@router.post("/api/v1/admin/matches/{match_id}/reset-pool")
async def reset_match_pool(
    match_id: int,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    await _sync_match_statuses(db)
    match = (await db.execute(select(Match).where(Match.id == match_id))).scalars().first()
    if not match:
        raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")
    if match.status != MatchStatus.upcoming or match.resolved_at is not None:
        raise HTTPException(status_code=400, detail="Chỉ có thể reset pool của trận chưa bắt đầu.")

    bets = (
        await db.execute(
            select(Bet).where(Bet.match_id == match_id).order_by(Bet.created_at.asc(), Bet.id.asc())
        )
    ).scalars().all()
    user_ids = list({bet.user_id for bet in bets})
    users_by_id = {
        item.id: item
        for item in (
            await db.execute(select(User).where(User.id.in_(user_ids)))
        ).scalars().all()
    } if user_ids else {}

    recipients: list[tuple[User, int]] = []
    total_refunded = 0

    try:
        for bet in bets:
            user_q = users_by_id.get(bet.user_id)
            if user_q:
                refund_points = int(bet.stake or 0)
                user_q.total_points = int(user_q.total_points or 0) + refund_points
                total_refunded += refund_points
                recipients.append((user_q, refund_points))
                db.add(user_q)
                await _record_point_transaction(
                    db,
                    user=user_q,
                    delta_points=refund_points,
                    transaction_type=PointTransactionType.bet_refund,
                    description=f"Hoàn điểm do admin reset pool: {match.home_team} vs {match.away_team}",
                    actor=admin_user,
                    match=match,
                )
            await db.delete(bet)

        await db.commit()
    except Exception as exc:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(exc))

    queued_notifications = 0
    try:
        for user_q, refund_points in recipients:
            await push_service.enqueue_web_push(
                db,
                user_id=user_q.id,
                title=f"Pool đã được reset: {match.home_team} vs {match.away_team}",
                body=f"Bạn đã được hoàn {refund_points:,} điểm. Hãy đặt lại trước khi trận bắt đầu.",
                url=f"/?match={match.id}",
                commit=False,
            )
            queued_notifications += 1
        await db.commit()
    except Exception:
        await db.rollback()
        logger.exception("Failed to enqueue reset-pool notifications for match %s", match_id)

    return {
        "message": f"Đã reset pool và hoàn {total_refunded:,} điểm cho {len(recipients)} người chơi.",
        "match_id": match_id,
        "reset_bet_count": len(bets),
        "refunded_points": total_refunded,
        "queued_notifications": queued_notifications,
    }

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
    has_home_penalty = payload.home_penalty_score is not None
    has_away_penalty = payload.away_penalty_score is not None
    if has_home_penalty != has_away_penalty:
        raise HTTPException(status_code=400, detail="Vui lòng nhập đủ tỷ số luân lưu cho cả hai đội.")

    try:
        # Lưu score
        match.home_score = payload.home_score
        match.away_score = payload.away_score
        match.home_penalty_score = payload.home_penalty_score
        match.away_penalty_score = payload.away_penalty_score

        # Tính adjusted score với handicap
        adjusted_home = payload.home_score + match.handicap
        adjusted_away = payload.away_score
        winning_choice = _resolve_market_winning_choice(match)

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
        settlement = _compute_two_way_settlement(match, bets) if match.handicap % 1 != 0 else None
        winning_bets = [b for b in bets if b.choice == winning_choice]
        stakes_on_winner = sum(b.stake for b in winning_bets)
        refunded = settlement["refunded"] if settlement is not None else (not winning_bets or stakes_on_winner == 0)

        if settlement is not None:
            for bet in bets:
                payout = settlement["payout_by_bet_id"].get(bet.id)
                bet.points_earned = payout
                db.add(bet)

                if payout is None:
                    payout_delta = bet.stake
                    transaction_type = PointTransactionType.bet_refund
                    description = f"Hoàn điểm trận: {match.home_team} vs {match.away_team}"
                elif payout > 0:
                    payout_delta = payout
                    transaction_type = PointTransactionType.bet_reward
                    description = f"Thưởng cược trận: {match.home_team} vs {match.away_team}"
                else:
                    continue

                user_q = users_by_id.get(bet.user_id)
                if user_q:
                    user_q.total_points += payout_delta
                    db.add(user_q)
                    await _record_point_transaction(
                        db,
                        user=user_q,
                        delta_points=payout_delta,
                        transaction_type=transaction_type,
                        description=description,
                        bet=bet,
                        match=match,
                    )
        elif refunded:
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

    await push_service.enqueue_match_resolved_notifications(db, match, bets, users_by_id)

    return {
        "message": f"Đã giải trận. Kết quả kèo: {winning_choice}.",
        "adjusted_score": f"{adjusted_home} - {adjusted_away}",
        "winning_choice": winning_choice,
        "total_pool": total_pool,
        "refunded": refunded,
    }
