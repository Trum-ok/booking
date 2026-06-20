import time

from fastapi import HTTPException, Request, status

from app.core.settings import get_settings


async def rate_limit(request: Request) -> None:
    settings = get_settings()
    redis = request.app.state.redis
    ident = request.client.host if request.client else "anonymous"
    window = int(time.time()) // settings.rate_limit_window_seconds
    key = f"ratelimit:{ident}:{window}"

    count = await redis.incr(key)
    if count == 1:
        await redis.expire(key, settings.rate_limit_window_seconds)

    if count > settings.rate_limit_times:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many requests",
        )
