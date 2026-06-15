from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base

# Đổi sang dùng SQLite và aiosqlite. 
# File database sẽ được tạo tại thư mục gốc của dự án với tên betting_db.db
DATABASE_URL = "sqlite+aiosqlite:///./betting_db.db"

# check_same_thread=False là cần thiết cho FastAPI + SQLite
engine = create_async_engine(
    DATABASE_URL, 
    echo=True,
    connect_args={"check_same_thread": False}
)

AsyncSessionLocal = sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

Base = declarative_base()

async def get_db():
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()