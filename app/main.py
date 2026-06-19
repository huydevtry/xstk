from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.lifecycle import shutdown_event, startup_event
from app.routers import admin, bets, community, leaderboard, matches, me, pages, settings, users


def create_app() -> FastAPI:
    app = FastAPI(title="Xác Suất & Thống Kê - Betting Engine")
    app.mount("/static", StaticFiles(directory="static"), name="static")

    app.include_router(pages.router)
    app.include_router(me.router)
    app.include_router(users.router)
    app.include_router(community.router)
    app.include_router(settings.router)
    app.include_router(matches.router)
    app.include_router(bets.router)
    app.include_router(leaderboard.router)
    app.include_router(admin.router)

    app.add_event_handler("startup", startup_event)
    app.add_event_handler("shutdown", shutdown_event)
    return app


app = create_app()
