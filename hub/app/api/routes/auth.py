from fastapi import APIRouter, Depends, Request, Response, status

from app.api.deps import auth_rate_limit, get_app_settings, get_auth_service, get_current_user
from app.core.config import Settings
from app.core.cookies import clear_session_cookie, set_session_cookie
from app.models.user import User
from app.schemas.auth import (
    AvatarUpload,
    LoginRequest,
    PasswordChange,
    PasswordResetRequest,
    ProfileUpdate,
    RegisterRequest,
    SetupRequest,
    SetupStatus,
    TokenResponse,
    UserOut,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/setup-status", response_model=SetupStatus)
async def setup_status(auth: AuthService = Depends(get_auth_service)) -> SetupStatus:
    return SetupStatus(needs_setup=await auth.needs_setup())


# setup/login/register set the HttpOnly session cookie used by the web panel
# and ALSO return the token in the body, so the CLI (Bearer header) keeps working.


@router.post("/setup", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def setup(
    body: SetupRequest,
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    user, token = await auth.setup_admin(body.email, body.name, body.password)
    set_session_cookie(response, token, settings, request)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def register(
    body: RegisterRequest,
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    user, token = await auth.register(body.invite_code, body.email, body.name, body.password)
    set_session_cookie(response, token, settings, request)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def login(
    body: LoginRequest,
    request: Request,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    user, token = await auth.login(body.email, body.password)
    set_session_cookie(response, token, settings, request)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.post(
    "/reset-password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(auth_rate_limit)],
)
async def reset_password(
    body: PasswordResetRequest,
    auth: AuthService = Depends(get_auth_service),
) -> None:
    # Public + token-gated: an admin-issued, single-use token sets a new password.
    # Rate-limited to blunt token guessing; generic error on an invalid token.
    await auth.reset_password(body.token, body.new_password)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    response: Response,
) -> None:
    # Idempotent and unauthenticated: it just expires the cookie. SameSite=Strict
    # already blocks a cross-site forced logout from carrying the session.
    clear_session_cookie(response, request)


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)


@router.patch("/me", response_model=UserOut)
async def update_me(
    body: ProfileUpdate,
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> UserOut:
    return UserOut.model_validate(await auth.update_profile(user, body.name))


@router.post(
    "/me/password",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(auth_rate_limit)],
)
async def change_password(
    body: PasswordChange,
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> None:
    # Rate-limited (same limiter as login) to blunt online guessing of the
    # current password.
    await auth.change_password(user, body.current_password, body.new_password)


@router.post("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def set_avatar(
    body: AvatarUpload,
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> None:
    await auth.set_avatar(user, body.image)


@router.delete("/me/avatar", status_code=status.HTTP_204_NO_CONTENT)
async def delete_avatar(
    user: User = Depends(get_current_user),
    auth: AuthService = Depends(get_auth_service),
) -> None:
    await auth.remove_avatar(user)
