import uuid
from datetime import datetime

from sqlalchemy import select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Booking, BookingStatus
from app.schemas import BookingCreate
from app.utils.exceptions import BookingNotCancellable, BookingNotFound


async def create_booking(session: AsyncSession, data: BookingCreate) -> Booking:
    booking = Booking(
        name=data.name,
        datetime=data.datetime,
        service_type=data.service_type,
        status=BookingStatus.pending,
    )
    session.add(booking)

    await session.commit()
    await session.refresh(booking)

    return booking


async def get_booking(session: AsyncSession, booking_id: uuid.UUID) -> Booking:
    booking = await session.get(Booking, booking_id)
    if booking is None:
        raise BookingNotFound(booking_id)
    return booking


async def list_bookings(
    session: AsyncSession,
    *,
    status: BookingStatus | None,
    limit: int,
    cursor: tuple[datetime, uuid.UUID] | None,
) -> tuple[list[Booking], tuple[datetime, uuid.UUID] | None]:
    """Keyset-пагинация по (created_at, id) DESC."""
    stmt = select(Booking)
    if status is not None:
        stmt = stmt.where(Booking.status == status)
    if cursor is not None:
        stmt = stmt.where(tuple_(Booking.created_at, Booking.id) < cursor)

    stmt = stmt.order_by(Booking.created_at.desc(), Booking.id.desc()).limit(limit + 1)
    rows = list(await session.scalars(stmt))

    items = rows[:limit]
    next_key = (items[-1].created_at, items[-1].id) if len(rows) > limit else None
    return items, next_key


async def cancel_booking(session: AsyncSession, booking_id: uuid.UUID) -> None:
    booking = await get_booking(session, booking_id)
    if booking.status is not BookingStatus.pending:
        raise BookingNotCancellable(booking.status)

    await session.delete(booking)
    await session.commit()
