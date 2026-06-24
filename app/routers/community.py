from fastapi import APIRouter
import asyncio
from app.services import push_service

from app.schemas.payloads import (
    AdminSettingsPayload,
    AdminUserPointsPayload,
    BetPayload,
    MatchPayload,
    ProfileCommentPayload,
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
    _get_profile_post_interactions,
    _normalize_profile_comment,
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
    ProfilePostLike,
    ProfilePostComment,
    PointTransaction,
    PointTransactionType,
    AppSetting,
    get_current_user,
    get_admin_user,
    get_request_user,
    ADMIN_EMAILS
)

router = APIRouter()

@router.get("/api/v1/community/timeline")
async def get_community_timeline(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    offset: int = Query(0, ge=0),
    limit: int = Query(DEFAULT_PROFILE_TIMELINE_PAGE_SIZE, ge=1, le=MAX_PROFILE_TIMELINE_PAGE_SIZE),
):
    return await _list_profile_status_posts(db, viewer_user_id=user.id, offset=offset, limit=limit)

async def _get_public_profile_post(db: AsyncSession, post_id: int) -> ProfileStatusPost:
    post = (
        await db.execute(
            select(ProfileStatusPost)
            .join(User, ProfileStatusPost.user_id == User.id)
            .where(ProfileStatusPost.id == post_id, User.is_approved.is_(True))
        )
    ).scalars().first()
    if not post:
        raise HTTPException(status_code=404, detail="Bài viết không tồn tại.")
    return post

async def _profile_post_interaction_payload(db: AsyncSession, post_id: int, user: User) -> dict:
    interactions = await _get_profile_post_interactions(db, [post_id], viewer_user_id=user.id)
    return {
        "post_id": post_id,
        "id": post_id,
        **interactions.get(post_id, {
            "like_count": 0,
            "viewer_liked": False,
            "liked_users": [],
            "comment_count": 0,
            "comments": [],
        }),
    }

@router.post("/api/v1/community/posts/{post_id}/like")
async def toggle_community_post_like(
    post_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_public_profile_post(db, post_id)
    existing = (
        await db.execute(
            select(ProfilePostLike).where(
                ProfilePostLike.post_id == post_id,
                ProfilePostLike.user_id == user.id,
            )
        )
    ).scalars().first()

    if existing:
        await db.delete(existing)
    else:
        db.add(ProfilePostLike(post_id=post_id, user_id=user.id))

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()

    result = await _profile_post_interaction_payload(db, post_id, user)

    # Push notification only when liking (not un-liking)
    if not existing:
        post = await _get_public_profile_post(db, post_id)
        asyncio.create_task(push_service.notify_post_liked(db, post, user))

    return result

@router.post("/api/v1/community/posts/{post_id}/comments", status_code=201)
async def create_community_post_comment(
    post_id: int,
    payload: ProfileCommentPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _get_public_profile_post(db, post_id)
    comment = ProfilePostComment(
        post_id=post_id,
        user_id=user.id,
        content=_normalize_profile_comment(payload.content),
    )
    db.add(comment)
    await db.commit()

    result = await _profile_post_interaction_payload(db, post_id, user)

    # Push notification to post owner + prior commenters
    post = await _get_public_profile_post(db, post_id)
    asyncio.create_task(push_service.notify_post_commented(db, post, user))

    return result
