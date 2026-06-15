from datetime import datetime

from pydantic import BaseModel, ConfigDict

# Bounds for the delegate frame payload (mirrored in bridge/src/shared/protocol.ts).
MAX_TASK_LEN = 2000
MAX_CONTEXT_LEN = 16384


class DelegationOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_agent: str
    to_agent: str
    task: str
    root_message_id: int | None
    result_message_id: int | None
    status: str
    created_at: datetime
    updated_at: datetime
