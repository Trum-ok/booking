import uuid

from app.models import BookingStatus


class BookingError(Exception):
    """Базовое доменное исключение брони."""


class BookingNotFound(BookingError):
    def __init__(self, booking_id: uuid.UUID) -> None:
        self.booking_id = booking_id
        super().__init__(f"Booking {booking_id} not found")


class BookingNotCancellable(BookingError):
    def __init__(self, status: BookingStatus) -> None:
        self.status = status
        super().__init__(f"Cannot cancel booking in status '{status.value}'")
