from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.agent import SLUG_PATTERN


class GroupCreate(BaseModel):
    slug: str = Field(pattern=SLUG_PATTERN, max_length=50)
    display_name: str = Field(min_length=1, max_length=120)


class GroupOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    display_name: str
    created_by: int
    created_at: datetime
    members: list[str] = []


class GroupMemberAdd(BaseModel):
    agent: str = Field(pattern=SLUG_PATTERN, max_length=50)


class BroadcastResult(BaseModel):
    """Resultado de um fan-out: quem recebeu, quem foi pulado (allowlist)."""

    group: str  # "@frontend-team" ou "@all"
    sent: list[str]
    skipped: list[str]
    message_ids: list[int]
