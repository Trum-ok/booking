import uuid
from datetime import datetime as datetime_t
from enum import StrEnum

from sqlalchemy import DateTime, Enum, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.db import Base


class BookingStatus(StrEnum):
    pending = "pending"
    confirmed = "confirmed"
    failed = "failed"


class Booking(Base):
    __tablename__ = "bookings"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255))
    datetime: Mapped[datetime_t] = mapped_column(DateTime(timezone=True))
    service_type: Mapped[str] = mapped_column(String(100))
    status: Mapped[BookingStatus] = mapped_column(
        Enum(BookingStatus, name="booking_status"),
        default=BookingStatus.pending,
    )
    created_at: Mapped[datetime_t] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime_t] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    __table_args__ = (
        Index("ix_bookings_status_created_at_id", "status", "created_at", "id"),
        Index("ix_bookings_created_at_id", "created_at", "id"),
    )
