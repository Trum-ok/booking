import uuid
from datetime import UTC, datetime
from operator import itemgetter
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models import Booking, BookingStatus
from app.schemas import BookingCreate


async def _create(client: AsyncClient, payload: dict[str, str]) -> str:
    response = await client.post("/bookings", json=payload)
    assert response.status_code == 201
    return response.json()["id"]


async def _page(
    client: AsyncClient,
    *,
    limit: int,
    cursor: str | None = None,
    status: str | None = None,
) -> Any:
    params: dict[str, str | int] = {"limit": limit}
    if cursor is not None:
        params["cursor"] = cursor
    if status is not None:
        params["status"] = status
    response = await client.get("/bookings", params=params)
    assert response.status_code == 200
    return response.json()


def _ids(page: Any) -> list[str]:
    return list(map(itemgetter("id"), page["items"]))


async def test_create_booking_returns_201_and_gets_confirmed(
    client: AsyncClient, booking_payload: dict[str, str]
):
    created = await client.post("/bookings", json=booking_payload)
    assert created.status_code == 201
    assert created.json()["name"] == "Alice"
    assert created.json()["status"] == BookingStatus.pending.value

    booking_id = created.json()["id"]
    fetched = await client.get(f"/bookings/{booking_id}")
    assert fetched.status_code == 200
    # Задача исполняется инлайн (failure_rate=0), поэтому статус уже confirmed.
    assert fetched.json()["status"] == BookingStatus.confirmed.value


async def test_create_booking_persists_correct_row(
    client: AsyncClient, session: AsyncSession, booking_payload: dict[str, str]
):
    created = await client.post("/bookings", json=booking_payload)
    booking_id = uuid.UUID(created.json()["id"])

    stored = await session.get(Booking, booking_id)
    assert stored is not None
    assert stored.name == "Alice"
    assert stored.service_type == "haircut"
    assert stored.datetime == datetime(2099, 1, 1, 10, tzinfo=UTC)
    assert stored.status is BookingStatus.confirmed


async def test_get_unknown_booking_returns_404(client: AsyncClient):
    resp = await client.get(f"/bookings/{uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"name": "", "datetime": "2030-01-01T10:00:00+00:00", "service_type": "x"},
        {"name": "Bob", "datetime": "not-a-date", "service_type": "x"},
        {"name": "Bob", "datetime": "2030-01-01T10:00:00+00:00"},
        # наивная дата без таймзоны
        {"name": "Bob", "datetime": "2030-01-01T10:00:00", "service_type": "x"},
        # дата в прошлом
        {"name": "Bob", "datetime": "2000-01-01T10:00:00+00:00", "service_type": "x"},
    ],
)
async def test_create_booking_validation_errors(
    client: AsyncClient, payload: dict[str, str]
):
    resp = await client.post("/bookings", json=payload)
    assert resp.status_code == 422


async def test_list_with_pagination_and_status_filter(
    client: AsyncClient, booking_payload: dict[str, str]
):
    await _create(client, booking_payload)
    await _create(client, booking_payload)
    await _create(client, booking_payload)

    first = await _page(client, limit=2)
    assert len(first["items"]) == 2
    assert first["limit"] == 2
    assert first["next_cursor"] is not None

    second = await _page(client, limit=2, cursor=first["next_cursor"])
    assert len(second["items"]) == 1
    assert second["next_cursor"] is None

    confirmed = await _page(client, limit=10, status="confirmed")
    assert len(confirmed["items"]) == 3

    failed = await _page(client, limit=10, status="failed")
    assert failed["items"] == []
    assert failed["next_cursor"] is None


async def test_pagination_pages_do_not_overlap(
    client: AsyncClient, booking_payload: dict[str, str]
):
    await _create(client, booking_payload)
    await _create(client, booking_payload)
    await _create(client, booking_payload)
    await _create(client, booking_payload)
    await _create(client, booking_payload)

    full = await _page(client, limit=5)
    page1 = await _page(client, limit=2)
    page2 = await _page(client, limit=2, cursor=page1["next_cursor"])
    page3 = await _page(client, limit=2, cursor=page2["next_cursor"])

    # Keyset проходит все строки по порядку, без пропусков и дублей даже при равных
    # created_at.
    assert _ids(page1) + _ids(page2) + _ids(page3) == _ids(full)
    assert len(_ids(full)) == 5
    assert len(set(_ids(full))) == 5
    assert page3["next_cursor"] is None


async def test_list_with_invalid_cursor_returns_422(client: AsyncClient):
    resp = await client.get("/bookings", params={"cursor": "!!!not-base64!!!"})
    assert resp.status_code == 422


async def test_delete_pending_booking_returns_204(
    client: AsyncClient, session: AsyncSession, booking_data: BookingCreate
):
    booking = await crud.create_booking(session, booking_data)
    booking_id = booking.id

    resp = await client.delete(f"/bookings/{booking_id}")
    assert resp.status_code == 204

    session.expunge_all()
    assert await session.get(Booking, booking_id) is None


async def test_delete_confirmed_booking_returns_409(
    client: AsyncClient, booking_payload: dict[str, str]
):
    booking_id = await _create(client, booking_payload)
    resp = await client.delete(f"/bookings/{booking_id}")
    assert resp.status_code == 409


async def test_delete_unknown_booking_returns_404(client: AsyncClient):
    resp = await client.delete(f"/bookings/{uuid.uuid4()}")
    assert resp.status_code == 404
