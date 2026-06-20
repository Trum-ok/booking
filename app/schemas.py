import uuid
from datetime import UTC, datetime
from typing import Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models import BookingStatus


class BookingCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    datetime: datetime
    service_type: str = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def _require_aware_future(self) -> Self:
        if self.datetime.tzinfo is None:
            raise ValueError("datetime must include a timezone offset")
        if self.datetime <= datetime.now(UTC):
            raise ValueError("datetime must be in the future")
        return self


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
