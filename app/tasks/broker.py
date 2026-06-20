from taskiq import AsyncBroker, SmartRetryMiddleware, TaskiqEvents, TaskiqState
from taskiq_redis import ListQueueBroker, RedisAsyncResultBackend

from app.core.logging import setup_logging
from app.core.settings import get_settings

settings = get_settings()


def _make_broker() -> AsyncBroker:
    broker = ListQueueBroker(settings.redis_url).with_result_backend(
        RedisAsyncResultBackend(settings.redis_url)
    )
    broker.add_middlewares(
        SmartRetryMiddleware(
            default_retry_count=settings.confirm_max_retries,
            default_delay=settings.confirm_retry_delay,
            use_delay_exponent=True,
            use_jitter=True,
            max_delay_exponent=60,
        )
    )
    return broker


broker = _make_broker()


@broker.on_event(TaskiqEvents.WORKER_STARTUP)
async def _setup_worker_logging(_: TaskiqState) -> None:
    setup_logging(settings.log_level)
