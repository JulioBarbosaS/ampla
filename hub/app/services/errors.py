"""Domain exceptions — services raise them, the API layer translates to HTTP."""


class DomainError(Exception):
    code = "domain_error"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class NotFoundError(DomainError):
    code = "not_found"


class ConflictError(DomainError):
    code = "conflict"


class PermissionDeniedError(DomainError):
    code = "permission_denied"


class AuthError(DomainError):
    """Invalid credentials — the message is always generic (never reveals
    whether the account exists)."""

    code = "auth_failed"


class AccountLockedError(DomainError):
    code = "account_locked"


class InvalidInputError(DomainError):
    code = "invalid_input"
