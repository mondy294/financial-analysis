from __future__ import annotations

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse


class ApiError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def raise_not_found(message: str) -> None:
    raise ApiError("NOT_FOUND", message, status_code=404)


def raise_bad_request(message: str) -> None:
    raise ApiError("BAD_REQUEST", message, status_code=400)


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": exc.code, "message": exc.message}},
    )


async def http_error_handler(_request: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": {"code": "HTTP_ERROR", "message": str(exc.detail)}},
    )
