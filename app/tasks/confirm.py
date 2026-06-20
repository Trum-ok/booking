import logging
import random
import uuid

from taskiq import Context, TaskiqDepends

from app.core.db import session_factory
from app.core.settings import get_settings
from app.models import Booking, BookingStatus
from app.tasks.broker import broker
from app.tasks.notifications import send_notification

logger = logging.getLogger("booking.worker")
settings = get_settings()


class ExternalServiceError(Exception):
    """Имитация сбоя внешнего сервиса подтверждения."""


async def call_external_service(failure_rate: float) -> None:
    """Mock-вызов внешнего сервиса; падает с заданной вероятностью."""
    if random.random() < failure_rate:
        raise ExternalServiceError("external confirmation service failed")


def _log(
    level: int,
    message: str,
    event: str,
    booking_id: uuid.UUID,
    **fields: object,
) -> None:
    """Structured-лог события задачи с обязательными event/booking_id."""
    logger.log(
        level,
        message,
        extra={"event": event, "booking_id": str(booking_id), **fields},
    )


async def _confirm(session, booking: Booking) -> BookingStatus:
    """Успех: фиксируем confirmed и шлём mock-уведомление."""
    booking.status = BookingStatus.confirmed
    await session.commit()
    await send_notification(booking.id, booking.name)
    _log(logging.INFO, "Booking confirmed", "confirm_ok", booking.id)
    return BookingStatus.confirmed


async def _handle_failure(
    session,
    booking: Booking,
    error: ExternalServiceError,
    *,
    is_last_attempt: bool,
) -> BookingStatus:
    booking_id = booking.id

    if not is_last_attempt:
        await session.rollback()
        _log(
            logging.WARNING,
            "Confirmation failed, will retry",
            "confirm_retry",
            booking_id,
        )
        raise error

    booking.status = BookingStatus.failed
    await session.commit()
    _log(
        logging.ERROR,
        "Confirmation failed permanently",
        "confirm_failed",
        booking_id,
    )
    return BookingStatus.failed


async def process_confirmation(
    session,
    booking_id: uuid.UUID,
    *,
    is_last_attempt: bool,
) -> BookingStatus | None:
    """Идемпотентное ядро подтверждения брони."""
    booking = await session.get(Booking, booking_id, with_for_update=True)

    if booking is None:
        _log(logging.WARNING, "Booking not found, skip", "confirm_skip", booking_id)
        return None
    if booking.status is not BookingStatus.pending:
        _log(
            logging.INFO,
            "Booking already processed, skip",
            "confirm_skip_idempotent",
            booking_id,
            status=booking.status.value,
        )
        return booking.status

    try:
        await call_external_service(settings.confirm_failure_rate)
    except ExternalServiceError as error:
        return await _handle_failure(
            session, booking, error, is_last_attempt=is_last_attempt
        )
    return await _confirm(session, booking)


def _is_last_attempt(context: Context) -> bool:
    labels = context.message.labels
    retries = int(labels.get("_retries", 0))
    max_retries = int(labels.get("max_retries", settings.confirm_max_retries))
    return retries + 1 >= max_retries


@broker.task(
    task_name="confirm_booking",
    retry_on_error=True,
    max_retries=settings.confirm_max_retries,
)
async def confirm_booking(
    booking_id: str,
    context: Context = TaskiqDepends(),
) -> str:
    async with session_factory() as session:
        result = await process_confirmation(
            session,
            uuid.UUID(booking_id),
            is_last_attempt=_is_last_attempt(context),
        )

    return result.value if result is not None else "skipped"
