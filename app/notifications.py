import asyncio
import html
import logging
import os
import ssl
import urllib.parse
import urllib.request
from pathlib import Path

import certifi
from dotenv import load_dotenv

from app.models import User


logger = logging.getLogger(__name__)
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _notification_env() -> tuple[str, str, str]:
    # Resolve .env lazily so Telegram notification does not depend on import order.
    load_dotenv(ENV_PATH, override=False)
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_ADMIN_CHAT_ID", "").strip()
    app_base_url = os.getenv("APP_BASE_URL", "").strip().rstrip("/")
    return token, chat_id, app_base_url


def _notification_ssl_context() -> ssl.SSLContext:
    cafile = (
        os.getenv("TELEGRAM_CA_BUNDLE", "").strip()
        or os.getenv("SSL_CERT_FILE", "").strip()
        or certifi.where()
    )
    return ssl.create_default_context(cafile=cafile)


def _send_telegram_message_sync(text: str) -> None:
    bot_token, admin_chat_id, _ = _notification_env()
    if not bot_token or not admin_chat_id:
        return
    ssl_context = _notification_ssl_context()
    data = urllib.parse.urlencode({
        "chat_id": admin_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": "true",
    }).encode("utf-8")
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{bot_token}/sendMessage",
        data=data,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    with urllib.request.urlopen(req, timeout=8, context=ssl_context) as response:
        response.read()


def _admin_url() -> str:
    _, _, app_base_url = _notification_env()
    return f"{app_base_url}/admin" if app_base_url else "/admin"


def _safe_user_label(user: User) -> str:
    display_name = (user.display_name or "").strip()
    if display_name:
        return f"{html.escape(display_name)} ({html.escape(user.email)})"
    return html.escape(user.email)


async def notify_admin_new_user_pending(user: User) -> None:
    bot_token, admin_chat_id, _ = _notification_env()
    if not bot_token or not admin_chat_id:
        return
    text = (
        "User mới đang chờ phê duyệt\n"
        f"User: {_safe_user_label(user)}\n"
        f"Tổng điểm hiện tại: {int(user.total_points or 0):,}\n"
        f"Trang admin: {_admin_url()}"
    )
    try:
        await asyncio.to_thread(_send_telegram_message_sync, text)
    except Exception:
        logger.exception("Failed to send Telegram new-user notification.")
