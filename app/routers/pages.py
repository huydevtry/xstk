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

@router.get("/", response_class=HTMLResponse)
async def read_home(request: Request, user: Optional[User] = Depends(get_request_user)):
    if user and not user.is_approved:
        return RedirectResponse(url="/guest", status_code=307)
    return templates.TemplateResponse(
        "index.html",
        _page_context(request, current_page="home", viewer=user),
        headers=NO_CACHE_HEADERS,
    )

@router.get("/guest", response_class=HTMLResponse)
async def read_guest(request: Request, user: Optional[User] = Depends(get_request_user)):
    if user and user.is_approved:
        return RedirectResponse(url="/", status_code=307)
    return templates.TemplateResponse(
        "guest.html",
        {
            "request": request,
            "asset_version": ASSET_VERSION,
            "pending_email": user.email if user else None,
            "pending_display_name": _user_display_name(user) if user else None,
            "logout_url": _logout_url_for_request(request),
        },
        headers=NO_CACHE_HEADERS,
    )

@router.get("/guide", response_class=HTMLResponse)
async def read_guide(request: Request):
    guide_path = Path(__file__).resolve().parents[2] / "guide.md"
    guide_markdown = guide_path.read_text(encoding="utf-8")
    return templates.TemplateResponse(
        "guide.html",
        _page_context(
            request,
            current_page="guide",
            guide_html=render_markdown(guide_markdown),
        ),
        headers=NO_CACHE_HEADERS,
    )

@router.get("/admin", response_class=HTMLResponse)
async def read_admin(request: Request, admin_user: User = Depends(get_admin_user)):
    return templates.TemplateResponse(
        "admin.html",
        {
            "request": request,
            "asset_version": ASSET_VERSION,
            "logout_url": _logout_url_for_request(request),
            "country_code_options_json": json.dumps(COUNTRY_CODE_OPTIONS, ensure_ascii=False),
        },
        headers=NO_CACHE_HEADERS,
    )

@router.get("/profile", response_class=HTMLResponse)
async def read_profile(request: Request, user: User = Depends(get_current_user)):
    current_page = "profile_public" if request.query_params.get("user_id") else "profile"
    return templates.TemplateResponse(
        "profile.html",
        _page_context(request, current_page=current_page, viewer=user),
        headers=NO_CACHE_HEADERS,
    )

@router.get("/community", response_class=HTMLResponse)
async def read_community(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse(
        "community.html",
        _page_context(request, current_page="community", viewer=user),
        headers=NO_CACHE_HEADERS,
    )

