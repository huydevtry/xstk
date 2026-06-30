import asyncio
from datetime import datetime, timedelta
import unittest

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import (
    Bet,
    Match,
    MatchStatus,
    Notification,
    NotificationJob,
    PointTransaction,
    PointTransactionType,
    PushSubscription,
    User,
)
from app.routers.admin import broadcast_admin_notification, reset_match_pool
from app.schemas.payloads import AdminBroadcastNotificationPayload
from app.services import push_service


class AdminNotificationResetTests(unittest.TestCase):
    def run_async(self, coro):
        return asyncio.run(coro)

    async def make_session(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
        session = session_factory()
        self.addCleanup(lambda: self.run_async(engine.dispose()))
        self.addCleanup(lambda: self.run_async(session.close()))
        return session

    async def seed_reset_case(self, db: AsyncSession, *, status=MatchStatus.upcoming):
        admin = User(email="admin@example.com", total_points=0, is_approved=True)
        user = User(email="player@example.com", total_points=900, is_approved=True)
        match = Match(
            home_team="Home",
            away_team="Away",
            handicap=0,
            status=status,
            start_time=datetime(2099, 1, 1, 12, 0, 0),
            end_time=datetime(2099, 1, 1, 14, 0, 0),
        )
        db.add_all([admin, user, match])
        await db.flush()
        bet = Bet(user_id=user.id, match_id=match.id, choice="HOME", stake=100)
        db.add(bet)
        await db.commit()
        return admin, user, match, bet

    def test_reset_pool_refunds_deletes_bets_and_queues_notifications(self):
        async def scenario():
            db = await self.make_session()
            admin, user, match, _bet = await self.seed_reset_case(db)

            result = await reset_match_pool(match.id, admin_user=admin, db=db)

            await db.refresh(user)
            bet_count = (
                await db.execute(select(func.count()).select_from(Bet).where(Bet.match_id == match.id))
            ).scalar_one()
            tx = (
                await db.execute(select(PointTransaction).where(PointTransaction.user_id == user.id))
            ).scalars().one()
            job = (
                await db.execute(select(NotificationJob).where(NotificationJob.recipient_user_id == user.id))
            ).scalars().one()

            self.assertEqual(result["reset_bet_count"], 1)
            self.assertEqual(result["refunded_points"], 100)
            self.assertEqual(user.total_points, 1000)
            self.assertEqual(bet_count, 0)
            self.assertEqual(tx.transaction_type, PointTransactionType.bet_refund)
            self.assertEqual(tx.delta_points, 100)
            self.assertEqual(tx.match_id, match.id)
            self.assertEqual(job.job_type, "web_push")

        self.run_async(scenario())

    def test_reset_pool_rejects_match_that_started(self):
        async def scenario():
            db = await self.make_session()
            admin, _user, match, _bet = await self.seed_reset_case(db, status=MatchStatus.live)

            with self.assertRaises(Exception) as raised:
                await reset_match_pool(match.id, admin_user=admin, db=db)

            self.assertEqual(getattr(raised.exception, "status_code", None), 400)

        self.run_async(scenario())

    def test_broadcast_targets_only_approved_users(self):
        async def scenario():
            db = await self.make_session()
            admin = User(email="admin@example.com", total_points=0, is_approved=True)
            approved = User(email="approved@example.com", total_points=0, is_approved=True)
            pending = User(email="pending@example.com", total_points=0, is_approved=False)
            db.add_all([admin, approved, pending])
            await db.commit()

            result = await broadcast_admin_notification(
                AdminBroadcastNotificationPayload(title="Hello", body="World", url="/community"),
                admin_user=admin,
                db=db,
            )

            jobs = (await db.execute(select(NotificationJob))).scalars().all()
            recipient_ids = {job.recipient_user_id for job in jobs}

            self.assertEqual(result["recipient_count"], 2)
            self.assertIn(admin.id, recipient_ids)
            self.assertIn(approved.id, recipient_ids)
            self.assertNotIn(pending.id, recipient_ids)

        self.run_async(scenario())

    def test_send_push_uses_latest_three_devices_per_user(self):
        async def scenario():
            db = await self.make_session()
            user = User(email="player@example.com", total_points=0, is_approved=True)
            db.add(user)
            await db.flush()
            base_time = datetime(2099, 1, 1, 12, 0, 0)
            for index in range(5):
                created_at = base_time + timedelta(minutes=index)
                db.add(
                    PushSubscription(
                        user_id=user.id,
                        endpoint=f"https://push.example/{index}",
                        p256dh="key",
                        auth="auth",
                        created_at=created_at,
                        updated_at=created_at,
                    )
                )
            await db.commit()

            sent_endpoints = []
            original_send = push_service._send_empty_push_sync
            push_service._send_empty_push_sync = lambda endpoint: sent_endpoints.append(endpoint) or True
            try:
                await push_service.send_push_to_users(db, [user.id], title="T", body="B", url="/")
            finally:
                push_service._send_empty_push_sync = original_send

            notification_count = (
                await db.execute(select(func.count()).select_from(Notification).where(Notification.user_id == user.id))
            ).scalar_one()

            self.assertEqual(notification_count, 1)
            self.assertEqual(
                sent_endpoints,
                ["https://push.example/4", "https://push.example/3", "https://push.example/2"],
            )

        self.run_async(scenario())


if __name__ == "__main__":
    unittest.main()
