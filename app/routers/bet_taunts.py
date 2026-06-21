from typing import Optional

from fastapi import APIRouter
from pydantic import BaseModel

from app.services.shared import (
    AsyncSession,
    Bet,
    Depends,
    HTTPException,
    Match,
    MatchStatus,
    User,
    _normalize_optional_taunt,
    _sync_match_statuses,
    get_current_user,
    get_db,
    select,
)

router = APIRouter()


class UpdateBetTauntPayload(BaseModel):
    taunt_text: Optional[str] = None


@router.get("/api/v1/bets/mine/{match_id}/taunt")
async def get_my_bet_taunt(
    match_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    bet = (
        await db.execute(
            select(Bet).where(Bet.match_id == match_id, Bet.user_id == user.id)
        )
    ).scalars().first()
    if not bet:
        raise HTTPException(status_code=404, detail="Bạn chưa đặt cược trận này.")

    return {"match_id": match_id, "taunt_text": bet.taunt_text or ""}


@router.put("/api/v1/bets/mine/{match_id}/taunt")
async def update_my_bet_taunt(
    match_id: int,
    payload: UpdateBetTauntPayload,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    await _sync_match_statuses(db)

    match = (await db.execute(select(Match).where(Match.id == match_id))).scalars().first()
    if not match:
        raise HTTPException(status_code=404, detail="Trận đấu không tồn tại.")
    if match.status != MatchStatus.upcoming:
        raise HTTPException(
            status_code=400,
            detail="Trận đã bắt đầu nên không thể sửa câu gáy.",
        )

    bet = (
        await db.execute(
            select(Bet).where(Bet.match_id == match_id, Bet.user_id == user.id)
        )
    ).scalars().first()
    if not bet:
        raise HTTPException(status_code=404, detail="Bạn chưa đặt cược trận này.")

    bet.taunt_text = _normalize_optional_taunt(payload.taunt_text)
    await db.commit()

    return {
        "message": "Đã cập nhật câu gáy.",
        "match_id": match_id,
        "taunt_text": bet.taunt_text or "",
    }
