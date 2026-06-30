import io
import unittest
import urllib.error
from datetime import datetime

from app.notifications import _describe_telegram_http_error
from app.services.shared import _serialize_utc_datetime


class TelegramNotificationErrorTests(unittest.TestCase):
    def test_describe_telegram_http_error_uses_api_description(self):
        exc = urllib.error.HTTPError(
            url="https://api.telegram.org/bot123/sendMessage",
            code=400,
            msg="Bad Request",
            hdrs=None,
            fp=io.BytesIO(b'{"ok":false,"description":"Bad Request: chat not found"}'),
        )

        self.assertEqual(
            _describe_telegram_http_error(exc),
            "HTTP 400: Bad Request: chat not found",
        )


class NotificationTimeSerializationTests(unittest.TestCase):
    def test_notification_time_is_serialized_as_utc_plus_seven(self):
        self.assertEqual(
            _serialize_utc_datetime(datetime(2026, 6, 30, 1, 2, 3)),
            "2026-06-30T08:02:03+07:00",
        )


if __name__ == "__main__":
    unittest.main()
