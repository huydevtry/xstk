from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.routers import admin, bets, community, leaderboard, matches, me, pages, settings, users
from app.schema_migrations import ensure_sqlite_schema


def create_app() -> FastAPI:
    app = FastAPI(title="Xác Suất & Thống Kê - Betting Engine")
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.on_event("startup")
    async def run_schema_migrations() -> None:
        await ensure_sqlite_schema()

    app.include_router(pages.router)
    app.include_router(me.router)
    app.include_router(users.router)
    app.include_router(community.router)
    app.include_router(settings.router)
    app.include_router(matches.router)
    app.include_router(bets.router)
    app.include_router(leaderboard.router)
    app.include_router(admin.router)

    return app


app = create_app()
