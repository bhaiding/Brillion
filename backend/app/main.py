import asyncio
import logging
from contextlib import asynccontextmanager, suppress

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
from sqlalchemy import select, text

from app.api.admin import router as admin_router
from app.api.rooms import router as rooms_router
from app.config import get_settings
from app.database import SessionLocal, engine
from app.game import advance_game, current_game, room_by_code, score_and_reveal
from app.models import GameState, Room, as_utc, utcnow
from app.rate_limit import RateLimitMiddleware
from app.realtime import hub
from app.worker import run as run_question_worker

settings = get_settings()
logger = logging.getLogger("brillion")


async def deadline_worker() -> None:
    while True:
        try:
            async with SessionLocal() as db:
                codes = list(
                    (
                        await db.scalars(
                            select(Room.code).where(
                                Room.state.in_(
                                    [
                                        GameState.QUESTION_PREVIEW,
                                        GameState.ANSWERING,
                                        GameState.REVEAL,
                                        GameState.LEADERBOARD,
                                    ]
                                ),
                                Room.closed_at.is_(None),
                                Room.expires_at > utcnow(),
                            )
                        )
                    ).all()
                )
            for code in codes:
                try:
                    async with hub.room_lock(code):
                        async with SessionLocal() as db:
                            room = await room_by_code(db, code, lock=True)
                            old_version = room.state_version
                            if room.state == GameState.ANSWERING:
                                await score_and_reveal(db, room)
                            elif room.state in {
                                GameState.QUESTION_PREVIEW,
                                GameState.REVEAL,
                                GameState.LEADERBOARD,
                            }:
                                game = await current_game(db, room)
                                if game and game.deadline_at and utcnow() >= as_utc(game.deadline_at):
                                    await advance_game(db, room)
                            if room.state_version != old_version:
                                await hub.publish(code, {"type": "state_changed", "room_code": code})
                except (TimeoutError, Exception):
                    logger.exception("deadline_transition_failed", extra={"room_code": code})
        except Exception:
            logger.exception("deadline_worker_failed")
        await asyncio.sleep(0.5)


@asynccontextmanager
async def lifespan(_: FastAPI):
    deadline_task = asyncio.create_task(deadline_worker())
    question_task = asyncio.create_task(run_question_worker()) if settings.inline_question_worker else None
    yield
    deadline_task.cancel()
    with suppress(asyncio.CancelledError):
        await deadline_task
    if question_task:
        question_task.cancel()
        with suppress(asyncio.CancelledError):
            await question_task
    await hub.close()
    await engine.dispose()


if settings.sentry_dsn:
    sentry_sdk.init(dsn=settings.sentry_dsn, environment=settings.environment)

app = FastAPI(
    title="Brillion API",
    version="1.0.0",
    description="Server-authoritative multiplayer rarity trivia",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Admin-Secret"],
)
app.add_middleware(RateLimitMiddleware)
app.include_router(rooms_router, prefix="/api")
app.include_router(admin_router, prefix="/api")
app.mount("/metrics", make_asgi_app())


@app.exception_handler(TimeoutError)
async def busy_handler(_: Request, exc: TimeoutError) -> JSONResponse:
    return JSONResponse(status_code=503, content={"detail": str(exc)})


@app.get("/health", tags=["operations"])
async def health() -> dict[str, str]:
    dependencies: dict[str, str] = {}
    try:
        async with SessionLocal() as db:
            await db.execute(text("SELECT 1"))
        dependencies["postgres"] = "ok"
    except Exception:
        dependencies["postgres"] = "unavailable"
    try:
        dependencies["redis"] = "ok" if await hub.ping() else "unavailable"
    except Exception:
        dependencies["redis"] = "unavailable"
    overall = "ok" if all(value == "ok" for value in dependencies.values()) else "degraded"
    return {"status": overall, **dependencies}


@app.get("/ready", tags=["operations"])
async def ready() -> JSONResponse:
    result = await health()
    return JSONResponse(status_code=200 if result["status"] == "ok" else 503, content=result)
