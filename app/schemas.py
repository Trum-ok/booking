import uuid
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import BookingStatus


class BookingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    datetime: datetime
    service_type: str = Field(min_length=1, max_length=100)

    @field_validator("datetime")
    @classmethod
    def _require_aware_future(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("datetime must include a timezone offset")
        if value <= datetime.now(UTC):
            raise ValueError("datetime must be in the future")
        return value


class BookingRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    datetime: datetime
    service_type: str
    status: BookingStatus
    created_at: datetime
    updated_at: datetime


class BookingList(BaseModel):
    items: list[BookingRead]
    limit: int
    next_cursor: str | None = None
