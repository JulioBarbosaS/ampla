from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class SetupRequest(BaseModel):
    email: EmailStr
    name: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=10, max_length=128)


class RegisterRequest(SetupRequest):
    invite_code: str = Field(min_length=8, max_length=24)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(max_length=128)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    name: str
    role: str
    created_at: datetime


class TokenResponse(BaseModel):
    token: str
    user: UserOut


class SetupStatus(BaseModel):
    needs_setup: bool
