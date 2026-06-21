from fastapi import APIRouter
from pydantic import ValidationError

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
    _normalize_external_media_payload,
    _save_feed_media_file,
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

def _parse_status_match_id(value) -> Optional[int]:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        return int(text)
    except ValueError:
        raise HTTPException(status_code=422, detail="match_id không hợp lệ.")

async def _read_profile_status_request(
    request: Request,
) -> tuple[str, Optional[int], Optional[UploadFile], Optional[str], Optional[str]]:
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].strip().lower()
    if content_type == "multipart/form-data":
        form = await request.form()
        media_candidate = form.get("media")
        media_file = media_candidate if getattr(media_candidate, "filename", "") else None
        return (
            str(form.get("content") or ""),
            _parse_status_match_id(form.get("match_id")),
            media_file,
            str(form.get("external_media_url") or ""),
            str(form.get("external_media_provider") or ""),
        )

    try:
        payload = ProfileStatusPostPayload(**await request.json())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=exc.errors())
    except ValueError:
        raise HTTPException(status_code=400, detail="Payload không hợp lệ.")
    return (
        payload.content,
        payload.match_id,
        None,
        payload.external_media_url,
        payload.external_media_provider,
    )

@router.get("/api/v1/me")
async def get_me(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    return await _build_profile_payload(user, db=db, include_badge=True)

@router.get("/api/v1/me/timeline")
async def get_my_timeline(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_PROFILE_TIMELINE_PAGE_SIZE, ge=1, le=MAX_PROFILE_TIMELINE_PAGE_SIZE),
):
    return await _list_profile_status_posts(db, user_id=user.id, offset=offset, limit=limit)

@router.get("/api/v1/me/point-transactions")
async def get_my_point_transactions(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_POINT_TRANSACTION_PAGE_SIZE, ge=1, le=MAX_POINT_TRANSACTION_PAGE_SIZE),
):
    return await _list_point_transactions(db, user_id=user.id, offset=offset, limit=limit)

@router.post("/api/v1/me/update-legacy")
async def update_me(
    payload: UpdateProfilePayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.display_name is not None:
        name = payload.display_name.strip()
        if len(name) < 1:
            raise HTTPException(status_code=400, detail="Tên hiển thị không được để trống.")
        if len(name) > 30:
            raise HTTPException(status_code=400, detail="Tên hiển thị tối đa 30 ký tự.")
        user.display_name = name
    if payload.default_taunt is not None:
        user.default_taunt = _normalize_optional_taunt(payload.default_taunt)
    if payload.profile_status is not None:
        content = _normalize_optional_profile_status(payload.profile_status)
        if content is not None:
            await _create_profile_status_post(db, user, content)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    base_name = user.email.split("@")[0]
    display_name = user.display_name or base_name
    return {
        "email": user.email,
        "display_name": display_name,
        "avatar_url": user.avatar_url,
        "avatar_color": user.avatar_color or "#6366f1",
        "initials": (display_name[:2]).upper(),
        "default_taunt": user.default_taunt,
        "profile_status": user.profile_status,
        "status_timeline": await _get_profile_status_timeline(db, user.id),
    }

@router.post("/api/v1/me/update")
async def update_me_v2(
    payload: UpdateProfilePayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fields = _provided_fields(payload)
    if "display_name" in fields:
        user.display_name = _normalize_display_name(payload.display_name)
    if "default_taunt" in fields:
        user.default_taunt = _normalize_optional_taunt(payload.default_taunt)
    if "profile_status" in fields:
        content = _normalize_optional_profile_status(payload.profile_status)
        if content is not None:
            await _create_profile_status_post(db, user, content)

    db.add(user)
    await db.commit()
    await db.refresh(user)

    display_name = _user_display_name(user)
    return {
        "email": user.email,
        "display_name": display_name,
        "avatar_url": user.avatar_url,
        "avatar_color": user.avatar_color or "#6366f1",
        "initials": _user_initials(user),
        "default_taunt": user.default_taunt,
        "profile_status": user.profile_status,
        "status_timeline": await _get_profile_status_timeline(db, user.id),
    }

@router.post("/api/v1/me/statuses", status_code=201)
async def create_profile_status(
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    raw_content, match_id, media_file, external_media_url, external_media_provider = await _read_profile_status_request(request)
    content = _normalize_optional_profile_status(raw_content)
    external_media = _normalize_external_media_payload(external_media_url, external_media_provider)
    if media_file is not None and external_media is not None:
        raise HTTPException(status_code=400, detail="Chỉ được chọn một nguồn media cho mỗi bài đăng.")
    if content is None and media_file is None and external_media is None:
        raise HTTPException(status_code=400, detail="Trạng thái hoặc ảnh/GIF không được để trống.")

    match = None
    post_type = PROFILE_POST_TYPE_TEXT
    bet_record = None
    if match_id is not None:
        match = (
            await db.execute(
                select(Match).where(Match.id == match_id)
            )
        ).scalars().first()
        if not match:
            raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")
        if not _match_result_published(match):
            raise HTTPException(status_code=400, detail="Chỉ được chia sẻ khi trận đã có kết quả chính thức.")

        bet_record = (
            await db.execute(
                select(Bet)
                .where(Bet.user_id == user.id, Bet.match_id == match.id)
                .limit(1)
            )
        ).scalars().first()
        if bet_record is None:
            raise HTTPException(status_code=400, detail="Bạn chưa đặt cược trận này nên chưa thể chia sẻ.")
        if await _has_match_reaction_post(db, user_id=user.id, match_id=match.id):
            raise HTTPException(status_code=400, detail="Bạn đã chia sẻ cảm nghĩ cho trận này rồi.")
        post_type = PROFILE_POST_TYPE_MATCH_REACTION

    media_payload = await _save_feed_media_file(media_file) if media_file is not None else external_media
    post = await _create_profile_status_post(
        db,
        user,
        content or "",
        post_type=post_type,
        match=match,
        media_url=media_payload["url"] if media_payload else None,
        media_content_type=media_payload["content_type"] if media_payload else None,
    )
    await db.commit()
    await db.refresh(post)
    await db.refresh(user)

    return {
        "status_post": _serialize_profile_status_post(post, author=user, match=match, bet=bet_record),
        "status_timeline": await _get_profile_status_timeline(db, user.id),
        "profile_status": user.profile_status,
    }

@router.post("/api/v1/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in AVATAR_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận ảnh JPG, PNG, WebP, GIF.")

    # Đọc toàn bộ nội dung file vào bộ nhớ (async-safe)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ảnh quá lớn, tối đa 5MB.")

    detected_type = _detect_image_content_type(contents)
    if detected_type != content_type:
        raise HTTPException(status_code=400, detail="Nội dung file không khớp định dạng ảnh.")

    # Tạo thư mục nếu chưa có
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    avatars_root = AVATARS_DIR.resolve()

    # Xóa ảnh cũ nếu tồn tại
    if user.avatar_url:
        old_path = Path(user.avatar_url.lstrip("/")).resolve()
        try:
            old_path.relative_to(avatars_root)
        except ValueError:
            old_path = None
        if old_path and old_path.is_file():
            old_path.unlink(missing_ok=True)

    # Lưu ảnh mới
    ext = AVATAR_CONTENT_TYPES[content_type]
    filename = f"{uuid_lib.uuid4().hex}.{ext}"
    dest = AVATARS_DIR / filename
    dest.write_bytes(contents)

    avatar_url = f"/static/avatars/{filename}"
    user.avatar_url = avatar_url
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"avatar_url": avatar_url}

@router.get("/api/v1/me/bets")
async def get_my_bets(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = (
        select(Bet, Match)
        .join(Match, Bet.match_id == Match.id)
        .where(Bet.user_id == user.id)
        .order_by(Bet.created_at.desc())
    )
    rows = (await db.execute(query)).all()
    reacted_match_ids = await _get_match_reaction_match_ids(
        db,
        user_id=user.id,
        match_ids=[row.Match.id for row in rows],
    )
    return [
        _serialize_bet_history_entry(
            bet=row.Bet,
            match=row.Match,
            can_share_reaction=_match_result_published(row.Match) and row.Match.id not in reacted_match_ids,
            has_shared_reaction=row.Match.id in reacted_match_ids,
        )
        for row in rows
    ]
