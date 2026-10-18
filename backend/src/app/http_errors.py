"""Map the CCU domain exceptions to a uniform JSON error body.

    {"error": {"type": "<slug>", "message": "<text>"}}
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.services.ccu.errors import (
    CcuBusy,
    CcuError,
    CcuUnreachable,
    CcuValidationError,
    RoomNotFound,
)

_STATUS = [
    (RoomNotFound, 404, "room_not_found"),
    (CcuBusy, 409, "busy"),
    (CcuValidationError, 422, "validation_error"),
    (CcuUnreachable, 503, "ccu_unreachable"),
    (CcuError, 502, "ccu_error"),
]


def _body(slug: str, message: str) -> dict:
    return {"error": {"type": slug, "message": message}}


def install_exception_handlers(app: FastAPI) -> None:
    def _make(status: int, slug: str):
        async def handler(_request: Request, exc: Exception) -> JSONResponse:
            return JSONResponse(status_code=status, content=_body(slug, str(exc)))

        return handler

    for exc_type, status, slug in _STATUS:
        app.add_exception_handler(exc_type, _make(status, slug))
