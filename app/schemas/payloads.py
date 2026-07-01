from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

from app.models import MatchStatus
from app.services.shared import MAX_HOMEPAGE_ANNOUNCEMENT_LENGTH, MAX_PROFILE_COMMENT_LENGTH, MAX_PROFILE_STATUS_LENGTH, MAX_TAUNT_LENGTH

class BetPayload(BaseModel):
    match_id: int
    choice: Literal["HOME", "DRAW", "AWAY"]
    stake: int = Field(..., ge=1)
    taunt_text: Optional[str] = Field(default=None, max_length=MAX_TAUNT_LENGTH)

class BetTauntPayload(BaseModel):
    taunt_text: Optional[str] = Field(default=None, max_length=MAX_TAUNT_LENGTH)

class UpdateBetPayload(BaseModel):
    choice: Literal["HOME", "DRAW", "AWAY"]
    stake: Optional[int] = Field(default=None, ge=1)
    taunt_text: Optional[str] = Field(default=None, max_length=MAX_TAUNT_LENGTH)

class ResolvePayload(BaseModel):
    home_score: int = Field(..., ge=0)
    away_score: int = Field(..., ge=0)
    home_penalty_score: Optional[int] = Field(default=None, ge=0)
    away_penalty_score: Optional[int] = Field(default=None, ge=0)

class MatchPayload(BaseModel):
    home_team: str = Field(..., min_length=1, max_length=80)
    away_team: str = Field(..., min_length=1, max_length=80)
    home_icon: Optional[str] = Field(default=None, max_length=500)
    away_icon: Optional[str] = Field(default=None, max_length=500)
    handicap: float = 0.0
    round: Optional[str] = Field(default=None, max_length=80)
    status: MatchStatus = MatchStatus.upcoming
    start_time: datetime
    end_time: Optional[datetime] = None

class AdminSettingsPayload(BaseModel):
    points_enabled: bool
    homepage_announcement: str = Field(default="", max_length=MAX_HOMEPAGE_ANNOUNCEMENT_LENGTH)

class AdminUserPointsPayload(BaseModel):
    total_points: int = Field(..., ge=0, le=1_000_000_000)
    reason: str = Field(..., min_length=1, max_length=280)

class AdminBroadcastNotificationPayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=120)
    body: str = Field(..., min_length=1, max_length=500)
    url: str = Field(default="/", max_length=500)

class UpdateProfilePayload(BaseModel):
    display_name: Optional[str] = None
    profile_status: Optional[str] = None

class ProfileStatusPostPayload(BaseModel):
    content: str = Field(..., max_length=MAX_PROFILE_STATUS_LENGTH)
    match_id: Optional[int] = None
    external_media_url: Optional[str] = Field(default=None, max_length=2000)
    external_media_provider: Optional[str] = Field(default=None, max_length=50)

class ProfileCommentPayload(BaseModel):
    content: str = Field(..., min_length=1, max_length=MAX_PROFILE_COMMENT_LENGTH)
