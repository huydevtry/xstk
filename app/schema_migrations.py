from sqlalchemy import text

import app.models  # noqa: F401
from app.database import Base, engine


async def _drop_legacy_users_columns(conn) -> None:
    await conn.execute(text("PRAGMA foreign_keys=OFF"))
    try:
        await conn.execute(text("""
            CREATE TABLE users__new (
                id CHAR(32) NOT NULL,
                email VARCHAR NOT NULL,
                display_name VARCHAR,
                total_points INTEGER,
                avatar_url VARCHAR,
                avatar_color VARCHAR,
                created_at DATETIME,
                is_approved BOOLEAN NOT NULL DEFAULT 0,
                approved_at DATETIME,
                last_seen_at DATETIME,
                previous_seen_at DATETIME,
                PRIMARY KEY (id),
                UNIQUE (email)
            )
        """))
        await conn.execute(text("""
            INSERT INTO users__new (
                id, email, display_name, total_points,
                avatar_url, avatar_color, created_at, is_approved,
                approved_at, last_seen_at, previous_seen_at
            )
            SELECT
                id, email, display_name, total_points,
                avatar_url, avatar_color, created_at, is_approved,
                approved_at, last_seen_at, previous_seen_at
            FROM users
        """))
        await conn.execute(text("DROP TABLE users"))
        await conn.execute(text("ALTER TABLE users__new RENAME TO users"))
    finally:
        await conn.execute(text("PRAGMA foreign_keys=ON"))


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

        if (
            "default_taunt" in existing_user_columns
            or "profile_status" in existing_user_columns
            or "approved_by_user_id" in existing_user_columns
        ):
            await _drop_legacy_users_columns(conn)
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
            "CREATE INDEX IF NOT EXISTS ix_users_is_approved_created_at ON users(is_approved, created_at DESC)",
            "CREATE INDEX IF NOT EXISTS ix_users_approved_points ON users(is_approved, total_points DESC)",
        ]
        for statement in index_statements:
            await conn.execute(text(statement))

        await conn.execute(text("PRAGMA optimize"))
