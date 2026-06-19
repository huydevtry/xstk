import asyncio
import logging
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import Base, engine
from app.models import Bet, Match, MatchStatus, User
from app.services.shared import (
    _backfill_point_transactions,
    _backfill_profile_status_timeline,
    _ensure_default_settings,
    _sync_match_statuses,
    _match_status_sync_loop,
)

logger = logging.getLogger(__name__)
match_status_sync_task: asyncio.Task | None = None

async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        match_columns = (
            await conn.exec_driver_sql("PRAGMA table_info(matches)")
        ).fetchall()
        match_column_names = {row[1] for row in match_columns}
        missing_match_columns = {
            "home_icon": "ALTER TABLE matches ADD COLUMN home_icon VARCHAR",
            "away_icon": "ALTER TABLE matches ADD COLUMN away_icon VARCHAR",
            "home_score": "ALTER TABLE matches ADD COLUMN home_score INTEGER DEFAULT 0",
            "away_score": "ALTER TABLE matches ADD COLUMN away_score INTEGER DEFAULT 0",
            "handicap": "ALTER TABLE matches ADD COLUMN handicap FLOAT DEFAULT 0.0",
            "status": "ALTER TABLE matches ADD COLUMN status VARCHAR DEFAULT 'upcoming'",
            "start_time": "ALTER TABLE matches ADD COLUMN start_time DATETIME",
            "end_time": "ALTER TABLE matches ADD COLUMN end_time DATETIME",
            "resolved_at": "ALTER TABLE matches ADD COLUMN resolved_at DATETIME",
        }
        for column_name, ddl in missing_match_columns.items():
            if column_name not in match_column_names:
                await conn.exec_driver_sql(ddl)

        user_columns = (
            await conn.exec_driver_sql("PRAGMA table_info(users)")
        ).fetchall()
        user_column_names = {row[1] for row in user_columns}
        if "default_taunt" not in user_column_names:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN default_taunt VARCHAR")
        if "profile_status" not in user_column_names:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN profile_status VARCHAR")
        if "is_approved" not in user_column_names:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN is_approved BOOLEAN DEFAULT 1")
        if "approved_at" not in user_column_names:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN approved_at DATETIME")
        if "approved_by_user_id" not in user_column_names:
            await conn.exec_driver_sql("ALTER TABLE users ADD COLUMN approved_by_user_id CHAR(32)")
        await conn.exec_driver_sql("UPDATE users SET is_approved = 1 WHERE is_approved IS NULL")
        await conn.exec_driver_sql(
            """
            UPDATE users
            SET approved_at = COALESCE(approved_at, created_at)
            WHERE is_approved = 1
            """
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_users_is_approved_created_at ON users (is_approved, created_at DESC)"
        )

        profile_status_columns = (
            await conn.exec_driver_sql("PRAGMA table_info(profile_status_posts)")
        ).fetchall()
        profile_status_column_names = {row[1] for row in profile_status_columns}
        if "post_type" not in profile_status_column_names:
            await conn.exec_driver_sql(
                "ALTER TABLE profile_status_posts ADD COLUMN post_type VARCHAR DEFAULT 'text'"
            )
        if "match_id" not in profile_status_column_names:
            await conn.exec_driver_sql(
                "ALTER TABLE profile_status_posts ADD COLUMN match_id INTEGER"
            )
        await conn.exec_driver_sql(
            """
            UPDATE profile_status_posts
            SET post_type = 'text'
            WHERE post_type IS NULL OR trim(post_type) = ''
            """
        )

        bet_columns = (
            await conn.exec_driver_sql("PRAGMA table_info(bets)")
        ).fetchall()
        bet_column_names = {row[1] for row in bet_columns}
        if "taunt_text" not in bet_column_names:
            await conn.exec_driver_sql("ALTER TABLE bets ADD COLUMN taunt_text VARCHAR")

        point_transaction_columns = (
            await conn.exec_driver_sql("PRAGMA table_info(point_transactions)")
        ).fetchall()
        point_transaction_column_names = {row[1] for row in point_transaction_columns}
        if point_transaction_columns and "is_backfilled" not in point_transaction_column_names:
            await conn.exec_driver_sql(
                "ALTER TABLE point_transactions ADD COLUMN is_backfilled BOOLEAN DEFAULT 1"
            )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_point_transactions_user_created_at ON point_transactions (user_id, created_at DESC, id DESC)"
        )
        await conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_point_transactions_type ON point_transactions (transaction_type)"
        )

        await conn.exec_driver_sql(
            """
            UPDATE matches
            SET end_time = datetime(start_time, '+2 hours')
            WHERE end_time IS NULL
            """
        )

        await conn.exec_driver_sql(
            """
            UPDATE bets
            SET points_earned = NULL
            WHERE points_earned = 0
              AND match_id IN (SELECT id FROM matches WHERE status != 'finished')
            """
        )
        await conn.exec_driver_sql(
            """
            UPDATE bets
            SET points_earned = NULL
            WHERE points_earned = 0
              AND match_id IN (
                  SELECT m.id
                  FROM matches m
                  WHERE m.status = 'finished'
                    AND EXISTS (SELECT 1 FROM bets b WHERE b.match_id = m.id)
                    AND NOT EXISTS (
                        SELECT 1
                        FROM bets b2
                        WHERE b2.match_id = m.id
                          AND b2.points_earned > 0
                    )
              )
            """
        )

        duplicate_bets = (
            await conn.exec_driver_sql(
                """
                SELECT 1
                FROM bets
                GROUP BY user_id, match_id
                HAVING COUNT(*) > 1
                LIMIT 1
                """
            )
        ).first()
        if duplicate_bets:
            logger.warning("Skip unique bet index because duplicate user/match bets already exist.")
        else:
            await conn.exec_driver_sql(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_bets_user_match ON bets (user_id, match_id)"
            )

    async with AsyncSession(engine) as session:
        await _ensure_default_settings(session)
        await _backfill_profile_status_timeline(session)
        await _backfill_point_transactions(session)
        result = await session.execute(select(Match))
        if not result.scalars().first():
            mock_matches = [
                Match(home_team="Vietnam", away_team="Thailand",
                      handicap=-0.5, status=MatchStatus.upcoming,
                      start_time=datetime(2026, 6, 20, 19, 0),
                      end_time=datetime(2026, 6, 20, 21, 0)),
                Match(home_team="Real Madrid", away_team="Barcelona",
                      handicap=-1.5, status=MatchStatus.upcoming,
                      start_time=datetime(2026, 6, 21, 2, 45),
                      end_time=datetime(2026, 6, 21, 4, 45)),
                Match(home_team="Man City", away_team="Man United",
                      handicap=0.5, status=MatchStatus.upcoming,
                      start_time=datetime(2026, 6, 22, 22, 0),
                      end_time=datetime(2026, 6, 23, 0, 0)),
            ]
            session.add_all(mock_matches)
            await session.commit()

    async with AsyncSession(engine) as session:
        await _sync_match_statuses(session)

    global match_status_sync_task
    if match_status_sync_task is None or match_status_sync_task.done():
        match_status_sync_task = asyncio.create_task(_match_status_sync_loop())

async def shutdown_event():
    global match_status_sync_task
    if match_status_sync_task and not match_status_sync_task.done():
        match_status_sync_task.cancel()
        try:
            await match_status_sync_task
        except asyncio.CancelledError:
            pass
    match_status_sync_task = None

