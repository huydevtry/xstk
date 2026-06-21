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
