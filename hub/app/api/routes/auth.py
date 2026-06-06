from fastapi import APIRouter, Depends

from app.api.deps import auth_rate_limit, get_auth_service, get_current_user
from app.models.user import User
from app.schemas.auth import (
    LoginRequest,
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


@router.post("/setup", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def setup(body: SetupRequest, auth: AuthService = Depends(get_auth_service)) -> TokenResponse:
    user, token = await auth.setup_admin(body.email, body.name, body.password)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.post("/register", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def register(
    body: RegisterRequest, auth: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    user, token = await auth.register(body.invite_code, body.email, body.name, body.password)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.post("/login", response_model=TokenResponse, dependencies=[Depends(auth_rate_limit)])
async def login(body: LoginRequest, auth: AuthService = Depends(get_auth_service)) -> TokenResponse:
    user, token = await auth.login(body.email, body.password)
    return TokenResponse(token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(user)
