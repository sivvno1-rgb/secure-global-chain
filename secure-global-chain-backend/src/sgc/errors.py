"""Domain errors and RFC-9457 problem+json rendering (API_SURFACE.md cross-cutting)."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class DomainError(Exception):
    """Base for service-layer errors mapped to HTTP problem responses."""

    status: int = 400
    title: str = "Bad Request"

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


class NotFoundError(DomainError):
    status = 404
    title = "Not Found"


class ConflictError(DomainError):
    status = 409
    title = "Conflict"


def _problem(status: int, title: str, detail: str, instance: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        media_type="application/problem+json",
        content={
            "type": "about:blank",
            "title": title,
            "status": status,
            "detail": detail,
            "instance": instance,
        },
    )


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain(request: Request, exc: DomainError) -> JSONResponse:
        return _problem(exc.status, exc.title, exc.detail, str(request.url))

    @app.exception_handler(HTTPException)
    async def _http(request: Request, exc: HTTPException) -> JSONResponse:
        title = {401: "Unauthorized", 403: "Forbidden", 404: "Not Found"}.get(
            exc.status_code, "Error"
        )
        response = _problem(
            exc.status_code, title, str(exc.detail), str(request.url)
        )
        if exc.headers:
            response.headers.update(exc.headers)
        return response

    @app.exception_handler(RequestValidationError)
    async def _validation(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _problem(422, "Unprocessable Entity", "Validation failed", str(request.url))
