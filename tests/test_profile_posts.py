import asyncio
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
import unittest
import uuid

from app.services.shared import (
    FEED_MEDIA_DIR,
    _delete_local_media_file,
    _delete_unused_feed_media,
    _serialize_profile_status_post,
)


def build_user(user_id):
    return SimpleNamespace(
        id=user_id,
        email="tester@example.com",
        display_name="Tester",
        avatar_url=None,
        avatar_color="#6366f1",
    )


def build_post(user_id, *, edited_at=None):
    return SimpleNamespace(
        id=42,
        user_id=user_id,
        post_type="text",
        content="Hello",
        media_url=None,
        media_content_type=None,
        created_at=datetime(2026, 1, 1, 12, 0, 0),
        edited_at=edited_at,
    )


class FakeScalarResult:
    def __init__(self, value):
        self.value = value

    def scalar(self):
        return self.value


class FakeDb:
    def __init__(self, reference_count):
        self.reference_count = reference_count

    async def execute(self, _query):
        return FakeScalarResult(self.reference_count)


class ProfilePostSerializerTests(unittest.TestCase):
    def test_serializer_exposes_edit_state_and_owner_edit_permission(self):
        user_id = uuid.uuid4()
        user = build_user(user_id)
        edited_at = datetime(2026, 1, 1, 12, 5, 0)

        payload = _serialize_profile_status_post(
            build_post(user_id, edited_at=edited_at),
            author=user,
            viewer_user_id=user_id,
        )

        self.assertTrue(payload["is_edited"])
        self.assertIsNotNone(payload["edited_at"])
        self.assertTrue(payload["can_edit"])

    def test_serializer_hides_edit_permission_for_other_viewers(self):
        user_id = uuid.uuid4()
        payload = _serialize_profile_status_post(
            build_post(user_id),
            author=build_user(user_id),
            viewer_user_id=uuid.uuid4(),
        )

        self.assertFalse(payload["is_edited"])
        self.assertIsNone(payload["edited_at"])
        self.assertFalse(payload["can_edit"])

    def test_serializer_hides_edit_permission_for_avatar_update_posts(self):
        user_id = uuid.uuid4()
        post = build_post(user_id)
        post.post_type = "avatar_update"

        payload = _serialize_profile_status_post(
            post,
            author=build_user(user_id),
            viewer_user_id=user_id,
        )

        self.assertEqual(payload["post_type"], "avatar_update")
        self.assertFalse(payload["can_edit"])


class ProfilePostMediaCleanupTests(unittest.TestCase):
    def test_delete_unused_feed_media_removes_unreferenced_local_file(self):
        FEED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"cleanup-{uuid.uuid4().hex}.txt"
        path = FEED_MEDIA_DIR / filename
        path.write_text("unused", encoding="utf-8")

        try:
            deleted = asyncio.run(
                _delete_unused_feed_media(FakeDb(0), f"/static/feed-media/{filename}")
            )
            self.assertTrue(deleted)
            self.assertFalse(path.exists())
        finally:
            path.unlink(missing_ok=True)

    def test_delete_unused_feed_media_keeps_referenced_local_file(self):
        FEED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"cleanup-{uuid.uuid4().hex}.txt"
        path = FEED_MEDIA_DIR / filename
        path.write_text("referenced", encoding="utf-8")

        try:
            deleted = asyncio.run(
                _delete_unused_feed_media(FakeDb(1), f"/static/feed-media/{filename}")
            )
            self.assertFalse(deleted)
            self.assertTrue(path.exists())
        finally:
            path.unlink(missing_ok=True)

    def test_delete_local_media_file_rejects_wrong_directory(self):
        FEED_MEDIA_DIR.mkdir(parents=True, exist_ok=True)
        filename = f"cleanup-{uuid.uuid4().hex}.txt"
        path = FEED_MEDIA_DIR / filename
        path.write_text("safe", encoding="utf-8")

        try:
            deleted = _delete_local_media_file(f"/static/feed-media/{filename}", Path("static/avatars"))
            self.assertFalse(deleted)
            self.assertTrue(path.exists())
        finally:
            path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
