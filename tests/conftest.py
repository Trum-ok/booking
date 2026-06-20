from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from taskiq import InMemoryBroker
from testcontainers.postgres import PostgresContainer

if TYPE_CHECKING:
    from app.schemas import BookingCreate

_PG_CONTAINER: pytest.StashKey[PostgresContainer] = pytest.StashKey()


def _ensure_docker_host() -> None:
    """Подхватить сокет из активного docker-контекста, если DOCKER_HOST пуст.

    Docker Desktop на macOS держит сокет в ~/.docker/run/docker.sock, а
    docker-py по умолчанию идёт в /var/run/docker.sock. На Linux/CI это no-op.
    """
    if os.environ.get("DOCKER_HOST"):
        return
    try:
        from docker.context import ContextAPI

        host = ContextAPI.get_current_context().endpoints["docker"]["Host"]
        if host:
            os.environ["DOCKER_HOST"] = host
    except Exception:
        pass


def pytest_configure(config: pytest.Config) -> None:
    """Поднять настоящий Postgres и настроить окружение ДО импорта приложения.

    Движок БД создаётся в момент импорта `app.core.db`, поэтому `DATABASE_URL`
    должен быть выставлен раньше — отсюда хук, а не фикстура. testcontainers сам
    управляет контейнером: отдельный `docker-compose up` для тестов не нужен,
    тесты идут против того же движка, что и прод (нативный Enum, FOR UPDATE).
    """
    _ensure_docker_host()
    # Ryuk-reaper спотыкается о нестандартный путь docker.sock на macOS;
    # контейнер гасим сами в pytest_unconfigure.
    os.environ.setdefault("TESTCONTAINERS_RYUK_DISABLED", "true")
    os.environ.setdefault("CONFIRM_FAILURE_RATE", "0")  # детерминированные тесты

    container = PostgresContainer("postgres:16-alpine", driver="asyncpg")
    container.start()
    os.environ["DATABASE_URL"] = container.get_connection_url()
    config.stash[_PG_CONTAINER] = container


def pytest_unconfigure(config: pytest.Config) -> None:
    container = config.stash.get(_PG_CONTAINER, None)
    if container is not None:
        container.stop()


@pytest.fixture(scope="session", autouse=True)
def test_broker() -> InMemoryBroker:
    from app.core.ratelimit import rate_limit
    from app.main import app
    from app.tasks.confirm import confirm_booking

    app.dependency_overrides[rate_limit] = lambda: None

    broker = InMemoryBroker(await_inplace=True)
    broker.register_task(
        confirm_booking.original_func,
        task_name=confirm_booking.task_name,
        **confirm_booking.labels,
    )
    confirm_booking.broker = broker
    return broker


@pytest_asyncio.fixture(autouse=True)
async def _reset_state(test_broker: InMemoryBroker) -> AsyncIterator[None]:
    from app.core.db import Base, engine

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    await test_broker.startup()

    yield

    await test_broker.shutdown()
    await engine.dispose()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def session() -> AsyncIterator[AsyncSession]:
    from app.core.db import session_factory

    async with session_factory() as s:
        yield s


@pytest.fixture
def booking_payload() -> dict[str, str]:
    return {
        "name": "Alice",
        "datetime": "2099-01-01T10:00:00+00:00",
        "service_type": "haircut",
    }


@pytest.fixture
def booking_data(booking_payload: dict[str, str]) -> BookingCreate:
    from app.schemas import BookingCreate

    return BookingCreate.model_validate(booking_payload)
