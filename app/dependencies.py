from fastapi import Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from dotenv import load_dotenv
from app.database import get_db
from app.models import User, AVATAR_COLORS
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
    if LOCAL_DEV_AUTH and LOCAL_DEV_EMAIL:
        emails.add(LOCAL_DEV_EMAIL)
    return emails


async def get_current_user(
    cf_email: str = Header(None, alias="Cf-Access-Authenticated-User-Email"),
    db: AsyncSession = Depends(get_db)
):
    if not cf_email:
        if not LOCAL_DEV_AUTH:
            raise HTTPException(
                status_code=401,
                detail="Yêu cầu truy cập thông qua Cloudflare Identity Gateway."
            )
        cf_email = LOCAL_DEV_EMAIL

    cf_email = cf_email.strip().lower()

    # Tìm kiếm user trong Database dựa vào Email từ Cloudflare Header cung cấp
    query = select(User).where(User.email == cf_email)
    result = await db.execute(query)
    user = result.scalars().first()

    # Nếu chưa tồn tại (User mới đăng nhập qua Cloudflare lần đầu), tiến hành tạo tự động
    if not user:
        user = User(
            email=cf_email,
            total_points=100,
            avatar_color=random.choice(AVATAR_COLORS)
        )
        db.add(user)

    # Luôn commit để kết thúc transaction ngầm (implicit transaction) từ hàm select ở trên,
    # tránh lỗi "A transaction is already begun on this Session" ở các route dùng db.begin()
    await db.commit()
    await db.refresh(user)

    return user


ADMIN_EMAILS = _load_admin_emails()


async def get_admin_user(current_user: User = Depends(get_current_user)):
    if current_user.email.strip().lower() not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=403,
            detail="Forbidden: Admin access required."
        )
    return current_user
