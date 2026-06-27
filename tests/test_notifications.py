import io
import unittest
import urllib.error

from app.notifications import _describe_telegram_http_error


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


if __name__ == "__main__":
    unittest.main()
