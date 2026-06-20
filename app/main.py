from contextlib import asynccontextmanager

import redis.asyncio as redis
from fastapi import FastAPI

from app.api.bookings import router as bookings_router
from app.api.errors import register_error_handlers
from app.core.logging import setup_logging
from app.core.settings import get_settings
from app.tasks.broker import broker


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    setup_logging(settings.log_level)

    if not broker.is_worker_process:
        await broker.startup()

    app.state.redis = redis.from_url(settings.redis_url, decode_responses=True)
    try:
        yield
    finally:
        await app.state.redis.aclose()
        if not broker.is_worker_process:
            await broker.shutdown()


app = FastAPI(title="Booking service", lifespan=lifespan)
register_error_handlers(app)
app.include_router(bookings_router)


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    return {"status": "ok"}
