from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.models import BookingStatus
from app.schemas import BookingCreate
from app.tasks import confirm as confirm_module
from app.tasks.confirm import ExternalServiceError, process_confirmation


async def test_confirm_success_sets_confirmed_and_notifies(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    booking_data: BookingCreate,
):
    booking = await crud.create_booking(session, booking_data)
    monkeypatch.setattr(confirm_module, "call_external_service", AsyncMock())
    notify = AsyncMock()
    monkeypatch.setattr(confirm_module, "send_notification", notify)

    result = await process_confirmation(session, booking.id, is_last_attempt=False)

    assert result is BookingStatus.confirmed
    await session.refresh(booking)
    assert booking.status is BookingStatus.confirmed
    notify.assert_awaited_once()


async def test_confirm_failed_on_last_attempt(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    booking_data: BookingCreate,
):
    booking = await crud.create_booking(session, booking_data)
    monkeypatch.setattr(
        confirm_module,
        "call_external_service",
        AsyncMock(side_effect=ExternalServiceError()),
    )

    result = await process_confirmation(session, booking.id, is_last_attempt=True)

    assert result is BookingStatus.failed
    await session.refresh(booking)
    assert booking.status is BookingStatus.failed


async def test_confirm_reraises_when_retries_remain(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    booking_data: BookingCreate,
):
    booking = await crud.create_booking(session, booking_data)
    monkeypatch.setattr(
        confirm_module,
        "call_external_service",
        AsyncMock(side_effect=ExternalServiceError()),
    )

    with pytest.raises(ExternalServiceError):
        await process_confirmation(session, booking.id, is_last_attempt=False)

    await session.refresh(booking)
    assert booking.status is BookingStatus.pending


async def test_confirm_is_idempotent_for_processed_booking(
    session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    booking_data: BookingCreate,
):
    booking = await crud.create_booking(session, booking_data)
    booking.status = BookingStatus.confirmed
    await session.commit()

    external = AsyncMock(side_effect=AssertionError("must not be called"))
    monkeypatch.setattr(confirm_module, "call_external_service", external)
    notify = AsyncMock()
    monkeypatch.setattr(confirm_module, "send_notification", notify)

    result = await process_confirmation(session, booking.id, is_last_attempt=True)

    assert result is BookingStatus.confirmed
    external.assert_not_awaited()
    notify.assert_not_awaited()
    await session.refresh(booking)
    assert booking.status is BookingStatus.confirmed
