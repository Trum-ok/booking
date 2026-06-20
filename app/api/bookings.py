import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app import crud
from app.core.db import get_session
from app.core.ratelimit import rate_limit
from app.models import BookingStatus
from app.schemas import BookingCreate, BookingList, BookingRead
from app.tasks.confirm import confirm_booking
from app.utils.pagination import InvalidCursor, decode_cursor, encode_cursor

router = APIRouter(prefix="/bookings", tags=["bookings"])


@router.post(
    "",
    response_model=BookingRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit)],
)
async def create_booking(
    data: BookingCreate,
    session: AsyncSession = Depends(get_session),
) -> BookingRead:
    booking = await crud.create_booking(session, data)
    await confirm_booking.kiq(str(booking.id))
    return BookingRead.model_validate(booking)


@router.get(
    "/{booking_id}",
    response_model=BookingRead,
    responses={404: {"description": "Booking not found"}},
)
async def get_booking(
    booking_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> BookingRead:
    booking = await crud.get_booking(session, booking_id)
    return BookingRead.model_validate(booking)


@router.get(
    "",
    response_model=BookingList,
    responses={422: {"description": "Invalid cursor"}},
)
async def list_bookings(
    session: AsyncSession = Depends(get_session),
    status_filter: BookingStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
) -> BookingList:
    decoded = None
    if cursor is not None:
        try:
            decoded = decode_cursor(cursor)
        except InvalidCursor:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Invalid cursor",
            ) from None

    items, has_more = await crud.list_bookings(
        session, status=status_filter, limit=limit, cursor=decoded
    )
    next_cursor = (
        encode_cursor(items[-1].created_at, items[-1].id)
        if has_more and items
        else None
    )
    return BookingList(
        items=[BookingRead.model_validate(i) for i in items],
        limit=limit,
        next_cursor=next_cursor,
    )


@router.delete(
    "/{booking_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={
        404: {"description": "Booking not found"},
        409: {"description": "Booking is not in 'pending' status"},
    },
)
async def cancel_booking(
    booking_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    await crud.cancel_booking(session, booking_id)
