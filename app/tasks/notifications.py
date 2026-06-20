import logging
import uuid

logger = logging.getLogger("booking.notifications")


async def send_notification(booking_id: uuid.UUID, name: str) -> None:
    """Mock-отправка уведомления о подтверждении брони."""
    logger.info(
        "Notification sent",
        extra={
            "event": "notification_sent",
            "booking_id": str(booking_id),
            "recipient": name,
        },
    )
