from datetime import datetime, timezone

from fastapi import Header, HTTPException, Depends
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from dotenv import load_dotenv
from app.database import get_db
from app.models import User, AVATAR_COLORS
from app.notifications import notify_admin_new_user_pending
import os
import random


load_dotenv()


def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _split_emails(value) -> set[str]:
    if not value:
        return set()
    return {email.strip().lower() for email in value.split(",") if email.strip()}


LOCAL_DEV_AUTH = _env_flag("LOCAL_DEV_AUTH")
LOCAL_DEV_EMAIL = os.getenv("LOCAL_DEV_EMAIL", "dev_local_test@domain.com").strip().lower()


def _load_admin_emails() -> set[str]:
    emails = _split_emails(os.getenv("ADMIN_EMAILS"))
    emails.update(_split_emails(os.getenv("ADMIN_EMAIL")))
    return emails


def _utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _normalize_identity(cf_email: str | None, cf_name: str | None, *, allow_anonymous: bool) -> tuple[str | None, str | None]:
    if not cf_email:
        if not LOCAL_DEV_AUTH:
            if allow_anonymous:
                return None, None
            raise HTTPException(
                status_code=401,
                detail="Yêu cầu truy cập thông qua Cloudflare Identity Gateway."
            )
        cf_email = LOCAL_DEV_EMAIL

    normalized_email = cf_email.strip().lower()
    normalized_name = (cf_name or "").strip() or None
    if normalized_name and len(normalized_name) > 30:
        normalized_name = normalized_name[:30].rstrip()
    return normalized_email, normalized_name


async def _resolve_user_record(
    *,
    cf_email: str | None,
    cf_name: str | None,
    db: AsyncSession,
    allow_anonymous: bool,
) -> User | None:
    normalized_email, normalized_name = _normalize_identity(
        cf_email,
        cf_name,
        allow_anonymous=allow_anonymous,
    )
    if not normalized_email:
        return None

    is_admin = normalized_email in ADMIN_EMAILS
    query = select(User).where(User.email == normalized_email)
    result = await db.execute(query)
    user = result.scalars().first()
    created_pending_user = False

    if not user:
        approved_at = _utc_now_naive() if is_admin else None
        user = User(
            email=normalized_email,
            display_name=normalized_name,
            total_points=0,
            avatar_color=random.choice(AVATAR_COLORS),
            is_approved=is_admin,
            approved_at=approved_at,
        )
        db.add(user)
        created_pending_user = not is_admin
    else:
        if not user.display_name and normalized_name:
            user.display_name = normalized_name
        if is_admin and not user.is_approved:
            user.is_approved = True
            user.approved_at = user.approved_at or _utc_now_naive()

    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        user = (await db.execute(query)).scalars().first()
        if not user:
            raise
        created_pending_user = False

    await db.refresh(user)
    if created_pending_user:
        await notify_admin_new_user_pending(user)

    return user


async def get_request_user(
    cf_email: str = Header(None, alias="Cf-Access-Authenticated-User-Email"),
    cf_name: str = Header(None, alias="Cf-Access-Authenticated-User-Name"),
    db: AsyncSession = Depends(get_db)
):
    return await _resolve_user_record(
        cf_email=cf_email,
        cf_name=cf_name,
        db=db,
        allow_anonymous=True,
    )


async def get_current_user(
    cf_email: str = Header(None, alias="Cf-Access-Authenticated-User-Email"),
    cf_name: str = Header(None, alias="Cf-Access-Authenticated-User-Name"),
    db: AsyncSession = Depends(get_db)
):
    user = await _resolve_user_record(
        cf_email=cf_email,
        cf_name=cf_name,
        db=db,
        allow_anonymous=False,
    )
    if user is None:
        raise HTTPException(
            status_code=401,
            detail="Yêu cầu truy cập thông qua Cloudflare Identity Gateway."
        )
    if not user.is_approved:
        raise HTTPException(
            status_code=403,
            detail="Tài khoản của bạn đang chờ admin phê duyệt."
        )

    return user


ADMIN_EMAILS = _load_admin_emails()


async def get_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.email.strip().lower() not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Admin access required."
        )
    return current_user
