from fastapi import Header, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.database import get_db
from app.models import User

async def get_current_user(
    cf_email: str = Header(None, alias="Cf-Access-Authenticated-User-Email"),
    db: AsyncSession = Depends(get_db)
):
    # Phục vụ cho việc test dưới Localhost khi không qua Cloudflare Tunnel
    if not cf_email:
        # Bạn có thể bật dòng dưới đây lên khi dev local để không bị chặn
        # cf_email = "dev_local_test@domain.com"
        raise HTTPException(
            status_code=401, 
            detail="Yêu cầu truy cập thông qua Cloudflare Identity Gateway."
        )
    
    # Tìm kiếm user trong Database dựa vào Email từ Cloudflare Header cung cấp
    query = select(User).where(User.email == cf_email)
    result = await db.execute(query)
    user = result.scalars().first()
    
    # Nếu chưa tồn tại (User mới đăng nhập qua Cloudflare lần đầu), tiến hành tạo tự động
    if not user:
        user = User(email=cf_email, total_points=1000)
        db.add(user)
        await db.commit()
        await db.refresh(user)
        
    return user