from fastapi import FastAPI, Depends, HTTPException, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import func, case, desc, update
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
from typing import Literal, Optional
import logging
import random
import uuid as uuid_lib
from pathlib import Path

from app.google_sheets import get_sheet_data
from dateutil import parser as date_parser

from app.database import engine, Base, get_db
from app.models import Match, MatchStatus, Bet, User
from app.dependencies import get_current_user, get_admin_user

logger = logging.getLogger(__name__)

app = FastAPI(title="Xác Suất & Thống Kê - Betting Engine")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# ─── Startup: tạo bảng & mock data ───────────────────────────────────────────

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
        result = await session.execute(select(Match))
        if not result.scalars().first():
            mock_matches = [
                Match(home_team="Vietnam", away_team="Thailand",
                      handicap=-0.5, status=MatchStatus.upcoming,
                      start_time=datetime(2026, 6, 20, 19, 0)),
                Match(home_team="Real Madrid", away_team="Barcelona",
                      handicap=-1.5, status=MatchStatus.upcoming,
                      start_time=datetime(2026, 6, 21, 2, 45)),
                Match(home_team="Man City", away_team="Man United",
                      handicap=0.5, status=MatchStatus.upcoming,
                      start_time=datetime(2026, 6, 22, 22, 0)),
            ]
            session.add_all(mock_matches)
            await session.commit()


# ─── Pydantic Schemas ─────────────────────────────────────────────────────────

class BetPayload(BaseModel):
    match_id: int
    choice: Literal["HOME", "DRAW", "AWAY"]
    stake: int = Field(..., ge=10)

class ResolvePayload(BaseModel):
    home_score: int = Field(..., ge=0)
    away_score: int = Field(..., ge=0)


# ─── Routes ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def read_home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin", response_class=HTMLResponse)
async def read_admin(request: Request, admin_user: User = Depends(get_admin_user)):
    return templates.TemplateResponse("admin.html", {"request": request})


@app.get("/profile", response_class=HTMLResponse)
async def read_profile(request: Request, user: User = Depends(get_current_user)):
    return templates.TemplateResponse("profile.html", {"request": request})


@app.get("/api/v1/me")
async def get_me(user: User = Depends(get_current_user)):
    base_name = user.email.split("@")[0]
    display_name = user.display_name or base_name
    initials = (display_name[:2]).upper()
    return {
        "email": user.email,
        "display_name": display_name,
        "total_points": user.total_points,
        "avatar_url": user.avatar_url,
        "avatar_color": user.avatar_color or "#6366f1",
        "initials": initials,
    }


# POST /api/v1/me/update — Cập nhật thông tin cá nhân (display_name)
# Dùng POST thay vì PATCH vì Cloudflare Access Gateway chặn PATCH/PUT/DELETE
class UpdateProfilePayload(BaseModel):
    display_name: Optional[str] = None

@app.post("/api/v1/me/update")
async def update_me(
    payload: UpdateProfilePayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if payload.display_name is not None:
        name = payload.display_name.strip()
        if len(name) < 1:
            raise HTTPException(status_code=400, detail="Tên hiển thị không được để trống.")
        if len(name) > 30:
            raise HTTPException(status_code=400, detail="Tên hiển thị tối đa 30 ký tự.")
        user.display_name = name
    db.add(user)
    await db.commit()
    await db.refresh(user)
    base_name = user.email.split("@")[0]
    display_name = user.display_name or base_name
    return {
        "email": user.email,
        "display_name": display_name,
        "avatar_url": user.avatar_url,
        "avatar_color": user.avatar_color or "#6366f1",
        "initials": (display_name[:2]).upper(),
    }


# POST /api/v1/me/avatar — Upload ảnh avatar
AVATARS_DIR = Path("static/avatars")
AVATAR_CONTENT_TYPES = {
    "image/jpeg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
}


def _detect_image_content_type(contents: bytes) -> Optional[str]:
    if contents.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if contents.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if contents.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if len(contents) >= 12 and contents[:4] == b"RIFF" and contents[8:12] == b"WEBP":
        return "image/webp"
    return None

@app.post("/api/v1/me/avatar")
async def upload_avatar(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    content_type = (file.content_type or "").split(";", 1)[0].strip().lower()
    if content_type not in AVATAR_CONTENT_TYPES:
        raise HTTPException(status_code=400, detail="Chỉ chấp nhận ảnh JPG, PNG, WebP, GIF.")

    # Đọc toàn bộ nội dung file vào bộ nhớ (async-safe)
    contents = await file.read()
    if len(contents) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ảnh quá lớn, tối đa 5MB.")

    detected_type = _detect_image_content_type(contents)
    if detected_type != content_type:
        raise HTTPException(status_code=400, detail="Nội dung file không khớp định dạng ảnh.")

    # Tạo thư mục nếu chưa có
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    avatars_root = AVATARS_DIR.resolve()

    # Xóa ảnh cũ nếu tồn tại
    if user.avatar_url:
        old_path = Path(user.avatar_url.lstrip("/")).resolve()
        try:
            old_path.relative_to(avatars_root)
        except ValueError:
            old_path = None
        if old_path and old_path.is_file():
            old_path.unlink(missing_ok=True)

    # Lưu ảnh mới
    ext = AVATAR_CONTENT_TYPES[content_type]
    filename = f"{uuid_lib.uuid4().hex}.{ext}"
    dest = AVATARS_DIR / filename
    dest.write_bytes(contents)

    avatar_url = f"/static/avatars/{filename}"
    user.avatar_url = avatar_url
    db.add(user)
    await db.commit()
    await db.refresh(user)

    return {"avatar_url": avatar_url}


# GET /api/v1/me/bets — Lịch sử cược của user hiện tại
@app.get("/api/v1/me/bets")
async def get_my_bets(user: User = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    query = (
        select(Bet, Match)
        .join(Match, Bet.match_id == Match.id)
        .where(Bet.user_id == user.id)
        .order_by(Bet.created_at.desc())
    )
    rows = (await db.execute(query)).all()
    return [
        {
            "bet_id": r.Bet.id,
            "match_id": r.Match.id,
            "home_team": r.Match.home_team,
            "home_icon": r.Match.home_icon,
            "away_team": r.Match.away_team,
            "away_icon": r.Match.away_icon,
            "match_status": r.Match.status,
            "home_score": r.Match.home_score,
            "away_score": r.Match.away_score,
            "handicap": r.Match.handicap,
            "start_time": r.Match.start_time.isoformat(),
            "choice": r.Bet.choice,
            "stake": r.Bet.stake,
            "points_earned": r.Bet.points_earned,
            "created_at": r.Bet.created_at.isoformat(),
        }
        for r in rows
    ]


# GET /api/v1/matches — Danh sách upcoming kèm pool stats per match
@app.get("/api/v1/matches")
async def get_upcoming_matches(db: AsyncSession = Depends(get_db)):
    # Subquery: tổng stake theo (match_id, choice)
    pool_q = (
        select(
            Bet.match_id,
            func.sum(case((Bet.choice == "HOME", Bet.stake), else_=0)).label("stakes_home"),
            func.sum(case((Bet.choice == "DRAW", Bet.stake), else_=0)).label("stakes_draw"),
            func.sum(case((Bet.choice == "AWAY", Bet.stake), else_=0)).label("stakes_away"),
            func.sum(Bet.stake).label("total_pool"),
        )
        .group_by(Bet.match_id)
        .subquery()
    )

    query = (
        select(
            Match,
            func.coalesce(pool_q.c.stakes_home, 0).label("stakes_home"),
            func.coalesce(pool_q.c.stakes_draw, 0).label("stakes_draw"),
            func.coalesce(pool_q.c.stakes_away, 0).label("stakes_away"),
            func.coalesce(pool_q.c.total_pool, 0).label("total_pool"),
        )
        .outerjoin(pool_q, Match.id == pool_q.c.match_id)
        .where(Match.status == MatchStatus.upcoming)
        .order_by(Match.start_time.asc())
    )

    rows = (await db.execute(query)).all()

    return [
        {
            "id": r.Match.id,
            "home_team": r.Match.home_team,
            "home_icon": r.Match.home_icon,
            "away_team": r.Match.away_team,
            "away_icon": r.Match.away_icon,
            "handicap": r.Match.handicap,
            "status": r.Match.status,
            "start_time": r.Match.start_time.isoformat(),
            "stakes_home": r.stakes_home,
            "stakes_draw": r.stakes_draw,
            "stakes_away": r.stakes_away,
            "total_pool": r.total_pool,
        }
        for r in rows
    ]


# POST /api/v1/bets — Đặt cược (Transaction)
@app.post("/api/v1/bets", status_code=201)
async def place_bet(
    payload: BetPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Validate match
    match = (await db.execute(
        select(Match).where(Match.id == payload.match_id)
    )).scalars().first()

    if not match:
        raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")
    if match.status != MatchStatus.upcoming:
        raise HTTPException(status_code=400, detail="Trận đấu không còn nhận cược.")

    # Validate balance
    if user.total_points < payload.stake:
        raise HTTPException(status_code=400, detail="Số điểm không đủ.")

    # Kiểm tra đã cược chưa (1 user / 1 match)
    existing = (await db.execute(
        select(Bet).where(Bet.user_id == user.id, Bet.match_id == payload.match_id)
    )).scalars().first()
    if existing:
        raise HTTPException(status_code=409, detail="Bạn đã đặt cược cho trận này.")

    try:
        balance_update = await db.execute(
            update(User)
            .where(User.id == user.id, User.total_points >= payload.stake)
            .values(total_points=User.total_points - payload.stake)
            .execution_options(synchronize_session=False)
        )
        if balance_update.rowcount != 1:
            await db.rollback()
            raise HTTPException(status_code=400, detail="Số điểm không đủ.")

        bet = Bet(
            user_id=user.id,
            match_id=payload.match_id,
            choice=payload.choice,
            stake=payload.stake,
            points_earned=None,
        )
        db.add(bet)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Bạn đã đặt cược cho trận này.")
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    await db.refresh(user)
    return {"message": "Đặt cược thành công.", "remaining_points": user.total_points}


# ─── GET /api/v1/matches/{match_id}/bets — Avatar Stack ──────────────────────
@app.get("/api/v1/matches/{match_id}/bets")
async def get_match_bets(match_id: int, db: AsyncSession = Depends(get_db)):
    """Trả về danh sách người đặt cược mỗi cửa (HOME/DRAW/AWAY) cho avatar stack."""
    query = (
        select(Bet, User)
        .join(User, Bet.user_id == User.id)
        .where(Bet.match_id == match_id)
        .order_by(Bet.created_at.asc())
    )
    rows = (await db.execute(query)).all()

    result = {"HOME": [], "DRAW": [], "AWAY": []}
    choice_counts = {"HOME": 0, "DRAW": 0, "AWAY": 0}

    for r in rows:
        choice_counts[r.Bet.choice] = choice_counts.get(r.Bet.choice, 0) + 1

    for r in rows:
        name = r.User.email.split("@")[0]
        initials = (name[:2]).upper()
        # Lone wolf: chỉ có 1 người đặt cửa này, trong khi cửa khác có nhiều hơn
        my_count = choice_counts.get(r.Bet.choice, 0)
        other_max = max(v for k, v in choice_counts.items() if k != r.Bet.choice)
        is_lone_wolf = my_count == 1 and other_max >= 3

        entry = {
            "name": name,
            "initials": initials,
            "stake": r.Bet.stake,
            "is_lone_wolf": is_lone_wolf,
        }
        result[r.Bet.choice].append(entry)

    return result


# ─── GET /api/v1/leaderboard — Bảng Phong Thần ───────────────────────────────
@app.get("/api/v1/leaderboard")
async def get_leaderboard(db: AsyncSession = Depends(get_db)):
    """Top 20 users với badges tự động và trend indicator."""
    # Lấy top 20 theo total_points
    users_q = (
        select(User)
        .order_by(desc(User.total_points))
        .limit(20)
    )
    users = (await db.execute(users_q)).scalars().all()

    # Tính points_earned trong 24h gần nhất (trend)
    since = datetime.utcnow() - timedelta(hours=24)
    trend_q = (
        select(Bet.user_id, func.sum(Bet.points_earned).label("earned_24h"))
        .where(Bet.created_at >= since, Bet.points_earned > 0)
        .group_by(Bet.user_id)
    )
    trend_rows = (await db.execute(trend_q)).all()
    trend_map = {str(r.user_id): r.earned_24h for r in trend_rows}

    # Tính streak thua liên tiếp
    streak_q = (
        select(Bet.user_id, Bet.points_earned, Bet.created_at)
        .where(Bet.match_id.in_(
            select(Bet.match_id).where(
                Bet.match_id.in_(
                    select(Bet.match_id).scalar_subquery()
                )
            )
        ))
        .order_by(Bet.user_id, desc(Bet.created_at))
    )
    # Đơn giản hơn: lấy bets gần nhất của mỗi user
    all_bets_q = (
        select(Bet.user_id, Bet.points_earned, Bet.created_at)
        .where(Bet.points_earned.is_not(None))
        .order_by(Bet.user_id, desc(Bet.created_at))
    )
    all_bets = (await db.execute(all_bets_q)).all()

    # Group bets by user, tính streak
    from collections import defaultdict
    user_bets = defaultdict(list)
    for b in all_bets:
        user_bets[str(b.user_id)].append(b.points_earned)

    def calc_loss_streak(bets):
        streak = 0
        for earned in bets:
            if earned == 0:
                streak += 1
            else:
                break
        return streak

    # Kiểm tra "Nhà tiên tri": thắng khi chọn cửa thiểu số
    contrarian_q = (
        select(
            Bet.user_id,
            Bet.match_id,
            Bet.choice,
            Bet.points_earned,
        )
        .where(Bet.points_earned > 0)
    )
    contrarian_bets = (await db.execute(contrarian_q)).all()

    # Đếm số người đặt mỗi cửa của mỗi trận
    choice_count_q = (
        select(Bet.match_id, Bet.choice, func.count(Bet.id).label("cnt"))
        .group_by(Bet.match_id, Bet.choice)
    )
    choice_counts = (await db.execute(choice_count_q)).all()
    choice_map = {}  # (match_id, choice) -> count
    for cc in choice_counts:
        choice_map[(cc.match_id, cc.choice)] = cc.cnt

    contrarian_users = set()
    for cb in contrarian_bets:
        my_cnt = choice_map.get((cb.match_id, cb.choice), 1)
        all_cnts = [v for (mid, ch), v in choice_map.items() if mid == cb.match_id]
        if all_cnts and my_cnt == min(all_cnts) and my_cnt < max(all_cnts):
            contrarian_users.add(str(cb.user_id))

    leaderboard = []
    for idx, user in enumerate(users):
        rank = idx + 1
        uid = str(user.id)
        streak_loss = calc_loss_streak(user_bets.get(uid, []))
        earned_24h = trend_map.get(uid, 0)
        trend = "up" if earned_24h > 0 else "down" if streak_loss > 0 else "neutral"
        is_contrarian = uid in contrarian_users

        # Badge logic
        if rank == 1:
            badge = {"label": "Đại gia", "emoji": "🤑", "color": "gold"}
        elif rank == len(users):
            badge = {"label": "Báo thủ", "emoji": "🐣", "color": "gray"}
        elif is_contrarian:
            badge = {"label": "Nhà tiên tri", "emoji": "🔮", "color": "purple"}
        elif streak_loss >= 3:
            badge = {"label": "Cứu rỗi", "emoji": "🙏", "color": "red"}
        else:
            badge = None

        leaderboard.append({
            "rank": rank,
            "name": user.email.split("@")[0],
            "total_points": user.total_points,
            "trend": trend,
            "earned_24h": earned_24h,
            "streak_loss": streak_loss,
            "badge": badge,
        })

    return leaderboard


# ─── GET /api/v1/activity-feed — Live Ticker ──────────────────────────────────
@app.get("/api/v1/activity-feed")
async def get_activity_feed(db: AsyncSession = Depends(get_db)):
    """20 hoạt động cược gần nhất để hiển thị trong Live Ticker."""
    query = (
        select(Bet, User, Match)
        .join(User, Bet.user_id == User.id)
        .join(Match, Bet.match_id == Match.id)
        .order_by(desc(Bet.created_at))
        .limit(20)
    )
    rows = (await db.execute(query)).all()

    TEMPLATES = [
        "🔥 {name} vừa tất tay {stake} điểm vào {team}",
        "💸 {name} đặt {stake} điểm chọn {team}",
        "🎯 {name} tin tưởng {team} với {stake} điểm",
        "🤡 {name} lại tiếp tục tin tưởng {team}",
        "😤 {name} quyết tâm với {team} — {stake} điểm",
        "🃏 {name} bài ngửa {stake} điểm vào {team}",
        "💰 {name} cược đậm {stake} điểm vào {team}",
    ]

    CHOICE_LABELS = {"HOME": "Chủ nhà", "DRAW": "Hòa", "AWAY": "Khách"}

    activities = []
    for r in rows:
        name = r.User.email.split("@")[0]
        team = (
            r.Match.home_team if r.Bet.choice == "HOME"
            else r.Match.away_team if r.Bet.choice == "AWAY"
            else CHOICE_LABELS["DRAW"]
        )
        tpl = random.choice(TEMPLATES)
        # Dùng seed ổn định để template không đổi mỗi lần refresh
        seed = hash(f"{r.Bet.id}{r.Bet.created_at}")
        tpl = TEMPLATES[abs(seed) % len(TEMPLATES)]
        text = tpl.format(name=name, stake=r.Bet.stake, team=team)
        activities.append({
            "text": text,
            "time": r.Bet.created_at.isoformat(),
        })

    return activities


# GET /api/v1/admin/matches — Danh sách tất cả trận đấu cho Admin
@app.get("/api/v1/admin/matches")
async def get_all_matches(admin_user: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    query = select(Match).order_by(Match.start_time.asc())
    rows = (await db.execute(query)).scalars().all()
    return [
        {
            "id": r.id,
            "home_team": r.home_team,
            "home_icon": r.home_icon,
            "away_team": r.away_team,
            "away_icon": r.away_icon,
            "home_score": r.home_score,
            "away_score": r.away_score,
            "handicap": r.handicap,
            "status": r.status,
            "start_time": r.start_time.isoformat(),
        }
        for r in rows
    ]


# POST /api/v1/admin/sync-matches
@app.post("/api/v1/admin/sync-matches")
async def sync_matches(admin_user: User = Depends(get_admin_user), db: AsyncSession = Depends(get_db)):
    try:
        records = get_sheet_data()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    try:
        for row in records:
            match_id = row.get("ID")
            if not match_id:
                continue

            home_team = row.get("Home Team", "Unknown")
            home_icon = row.get("Home Icon") or None
            away_team = row.get("Away Team", "Unknown")
            away_icon = row.get("Away Icon") or None
            handicap = float(row.get("Handicap", 0.0))

            try:
                start_time = date_parser.parse(str(row.get("Start Time")))
            except (TypeError, ValueError):
                start_time = datetime.utcnow()

            existing = (await db.execute(select(Match).where(Match.id == match_id))).scalars().first()
            if existing:
                existing.home_team = home_team
                existing.home_icon = home_icon
                existing.away_team = away_team
                existing.away_icon = away_icon
                existing.handicap = handicap
                existing.start_time = start_time
                db.add(existing)
            else:
                new_match = Match(
                    id=match_id,
                    home_team=home_team,
                    home_icon=home_icon,
                    away_team=away_team,
                    away_icon=away_icon,
                    handicap=handicap,
                    start_time=start_time,
                    status=MatchStatus.upcoming
                )
                db.add(new_match)

        await db.commit()
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return {"message": f"Đã đồng bộ {len(records)} trận đấu từ Google Sheets thành công."}


# POST /api/v1/admin/resolve-match/{match_id} — Giải trận
@app.post("/api/v1/admin/resolve-match/{match_id}")
async def resolve_match(
    match_id: int,
    payload: ResolvePayload,
    admin_user: User = Depends(get_admin_user),
    db: AsyncSession = Depends(get_db),
):
    match = (await db.execute(
        select(Match).where(Match.id == match_id)
    )).scalars().first()

    if not match:
        raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")
    if match.status == MatchStatus.finished:
        raise HTTPException(status_code=400, detail="Trận đã được giải trước đó.")

    try:
        # Lưu score
        match.home_score = payload.home_score
        match.away_score = payload.away_score

        # Tính adjusted score với handicap
        adjusted_home = payload.home_score + match.handicap
        adjusted_away = payload.away_score

        if adjusted_home > adjusted_away:
            winning_choice = "HOME"
        elif adjusted_home < adjusted_away:
            winning_choice = "AWAY"
        else:
            winning_choice = "DRAW"

        # Lấy tất cả bets của trận
        bets = (await db.execute(
            select(Bet).where(Bet.match_id == match_id)
        )).scalars().all()

        total_pool = sum(b.stake for b in bets)
        winning_bets = [b for b in bets if b.choice == winning_choice]
        stakes_on_winner = sum(b.stake for b in winning_bets)
        refunded = not winning_bets or stakes_on_winner == 0

        if refunded:
            # Refund tất cả nếu không có ai cược đúng
            for bet in bets:
                bet.points_earned = None
                db.add(bet)
                user_q = (await db.execute(
                    select(User).where(User.id == bet.user_id)
                )).scalars().first()
                if user_q:
                    user_q.total_points += bet.stake
                    db.add(user_q)
        else:
            # Multiplier = total_pool / stakes_on_winner
            multiplier = total_pool / stakes_on_winner
            for bet in bets:
                bet.points_earned = 0
                db.add(bet)

            for bet in winning_bets:
                reward = int(bet.stake * multiplier)  # Math.floor equivalent
                bet.points_earned = reward
                db.add(bet)

                user_q = (await db.execute(
                    select(User).where(User.id == bet.user_id)
                )).scalars().first()
                if user_q:
                    user_q.total_points += reward
                    db.add(user_q)

        match.status = MatchStatus.finished
        db.add(match)
        await db.commit()

    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

    return {
        "message": f"Đã giải trận. Kết quả kèo: {winning_choice}.",
        "adjusted_score": f"{adjusted_home} - {adjusted_away}",
        "winning_choice": winning_choice,
        "total_pool": total_pool,
        "refunded": refunded,
    }
