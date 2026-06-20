import base64
import binascii
import uuid
from datetime import datetime


class InvalidCursor(ValueError):
    """Курсор пагинации не удалось декодировать."""


def encode_cursor(created_at: datetime, booking_id: uuid.UUID) -> str:
    raw = f"{created_at.isoformat()}|{booking_id}"
    return base64.urlsafe_b64encode(raw.encode()).decode()


def decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        created_at_str, id_str = raw.split("|", 1)
        return datetime.fromisoformat(created_at_str), uuid.UUID(id_str)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise InvalidCursor("invalid cursor") from exc
