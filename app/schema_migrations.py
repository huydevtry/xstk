from sqlalchemy import text

import app.models  # noqa: F401
from app.database import Base, engine


async def ensure_sqlite_schema() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

        result = await conn.execute(text("PRAGMA table_info(profile_status_posts)"))
        existing_columns = {row[1] for row in result.fetchall()}

        if "media_url" not in existing_columns:
            await conn.execute(text("ALTER TABLE profile_status_posts ADD COLUMN media_url VARCHAR"))
        if "media_content_type" not in existing_columns:
            await conn.execute(text("ALTER TABLE profile_status_posts ADD COLUMN media_content_type VARCHAR"))
        if "edited_at" not in existing_columns:
            await conn.execute(text("ALTER TABLE profile_status_posts ADD COLUMN edited_at DATETIME"))

        result = await conn.execute(text("PRAGMA table_info(users)"))
        existing_user_columns = {row[1] for row in result.fetchall()}

        if "last_seen_at" not in existing_user_columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN last_seen_at DATETIME"))
        if "previous_seen_at" not in existing_user_columns:
            await conn.execute(text("ALTER TABLE users ADD COLUMN previous_seen_at DATETIME"))

        # push_subscriptions table is created by Base.metadata.create_all above (PushSubscription model)
        # No manual migration needed — SQLAlchemy handles it via create_all.

        index_statements = [
            "CREATE INDEX IF NOT EXISTS ix_bets_user_created ON bets(user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS ix_bets_match_created ON bets(match_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS ix_bets_match_choice ON bets(match_id, choice)",
            "CREATE INDEX IF NOT EXISTS ix_matches_status_start ON matches(status, start_time)",
            "CREATE INDEX IF NOT EXISTS ix_profile_posts_user_created ON profile_status_posts(user_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS ix_profile_posts_match_created ON profile_status_posts(match_id, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS ix_users_email ON users(email)",
            "CREATE INDEX IF NOT EXISTS ix_users_approved_points ON users(is_approved, total_points DESC)",
        ]
        for statement in index_statements:
            await conn.execute(text(statement))

        await conn.execute(text("PRAGMA optimize"))
