from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.routers import admin, bets, community, leaderboard, matches, me, pages, push, settings, users
from app.schema_migrations import ensure_sqlite_schema

_SW_PATH = Path(__file__).resolve().parents[1] / "static" / "sw.js"


def create_app() -> FastAPI:
    app = FastAPI(title="Xác Suất & Thống Kê - Betting Engine")
    app.mount("/static", StaticFiles(directory="static"), name="static")

    @app.get("/sw.js", include_in_schema=False)
    async def serve_sw():
        """
        Serve the Service Worker from the root path so its scope can cover '/'.
        The Service-Worker-Allowed header explicitly grants full-site scope.
        """
        return FileResponse(
            _SW_PATH,
            media_type="application/javascript",
            headers={"Service-Worker-Allowed": "/"},
        )

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
    app.include_router(push.router)

    return app


app = create_app()
