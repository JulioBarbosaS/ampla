"""Session cookie for the web panel.

The panel authenticates with an HttpOnly cookie so the JWT is never reachable
from JavaScript — an XSS in the panel cannot exfiltrate the session token (the
residual risk left by storing it in localStorage).

SameSite=Strict is the CSRF control: the browser never attaches the cookie to
cross-site requests, so a malicious page cannot ride an authenticated session.
For a single-origin self-hosted deployment this is sufficient; no double-submit
token is needed. `Secure` follows the REQUEST scheme, not the environment: it is
set only when the connection is HTTPS (directly, or via a TLS proxy that sets
`X-Forwarded-Proto`, which ProxyHeadersMiddleware reflects into the scheme). A
`Secure` cookie would be silently dropped over plain `http://localhost`, which
is exactly the URL the quickstart tells you to open — so gating it on the scheme
keeps localhost-over-HTTP working while real HTTPS deployments still get it.

Programmatic clients (the CLI, the tests) keep using the `Authorization: Bearer`
header instead — see get_current_user, which accepts either, header first.
"""

from fastapi import Request, Response

from app.core.config import Settings

SESSION_COOKIE = "amp_session"


def _secure(request: Request) -> bool:
    return request.url.scheme == "https"


def set_session_cookie(
    response: Response, token: str, settings: Settings, request: Request
) -> None:
    response.set_cookie(
        key=SESSION_COOKIE,
        value=token,
        max_age=settings.jwt_expires_days * 24 * 3600,
        httponly=True,
        samesite="strict",
        secure=_secure(request),
        path="/",
    )


def clear_session_cookie(response: Response, request: Request) -> None:
    response.delete_cookie(
        key=SESSION_COOKIE,
        httponly=True,
        samesite="strict",
        secure=_secure(request),
        path="/",
    )
