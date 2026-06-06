"""Tradução de exceções de domínio para respostas HTTP."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.services.errors import (
    AccountLockedError,
    AuthError,
    ConflictError,
    DomainError,
    InvalidInputError,
    NotFoundError,
    PermissionDeniedError,
)

_STATUS_BY_TYPE: list[tuple[type[DomainError], int]] = [
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (PermissionDeniedError, status.HTTP_403_FORBIDDEN),
    (AuthError, status.HTTP_401_UNAUTHORIZED),
    (AccountLockedError, status.HTTP_429_TOO_MANY_REQUESTS),
    (InvalidInputError, status.HTTP_422_UNPROCESSABLE_CONTENT),
]


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        for error_type, http_status in _STATUS_BY_TYPE:
            if isinstance(exc, error_type):
                return JSONResponse(
                    status_code=http_status,
                    content={"code": exc.code, "detail": exc.detail},
                )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"code": exc.code, "detail": exc.detail},
        )
