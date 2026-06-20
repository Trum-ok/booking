from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.exceptions import BookingNotCancellable, BookingNotFound


async def _not_found(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"detail": "Booking not found"},
    )


async def _not_cancellable(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": str(exc)},
    )


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(BookingNotFound, _not_found)
    app.add_exception_handler(BookingNotCancellable, _not_cancellable)
