from datetime import datetime

from pydantic import BaseModel, ConfigDict


class InviteOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    code: str
    created_at: datetime
    expires_at: datetime
    used_by: int | None
    used_at: datetime | None
