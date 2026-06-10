from fastapi import APIRouter, Depends, Response, status

from app.api.deps import auth_rate_limit, get_app_settings, get_auth_service, get_current_user
from app.core.config import Settings
from app.core.cookies import clear_session_cookie, set_session_cookie
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
    PasswordChange,
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
    response: Response,
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    user, token = await auth.setup_admin(body.email, body.name, body.password)
    set_session_cookie(response, token, settings)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def register(
    body: RegisterRequest,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    user, token = await auth.register(body.invite_code, body.email, body.name, body.password)
    set_session_cookie(response, token, settings)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def login(
    body: LoginRequest,
    response: Response,
    auth: AuthService = Depends(get_auth_service),
    settings: Settings = Depends(get_app_settings),
) -> TokenResponse:
    user, token = await auth.login(body.email, body.password)
    set_session_cookie(response, token, settings)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    settings: Settings = Depends(get_app_settings),
) -> None:
    # Idempotent and unauthenticated: it just expires the cookie. SameSite=Strict
    # already blocks a cross-site forced logout from carrying the session.
    clear_session_cookie(response, settings)


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
