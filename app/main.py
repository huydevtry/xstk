from fastapi import FastAPI, Depends
from app.database import engine, Base
from app.dependencies import get_current_user
from app.models import User

app = FastAPI(title="Football Betting Realtime Engine")

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

@app.get("/")
async def hello_world():
    return {"message": "Hello World - Betting Engine Ready"}

# Endpoint yêu cầu đăng nhập, trả về profile và số điểm hiện tại của user
@app.get("/api/v1/me")
async def get_user_profile(current_user: User = Depends(get_current_user)):
    return {
        "user_id": str(current_user.id),
        "email": current_user.email,
        "total_points": current_user.total_points,
        "created_at": current_user.created_at
    }