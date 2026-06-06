"""Exceções de domínio — services lançam, camada API traduz para HTTP."""


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
    """Credenciais inválidas — mensagem sempre genérica (não revela se a conta existe)."""

    code = "auth_failed"


class AccountLockedError(DomainError):
    code = "account_locked"


class InvalidInputError(DomainError):
    code = "invalid_input"
