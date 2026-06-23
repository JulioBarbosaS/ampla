"""Scheduled agent task schemas (Epic 08). The `prompt` is owner-authored
(trusted), but still bounded; the (kind, spec) pair is validated by the service
via app.services.scheduler.validate_spec before it is stored."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

SCHEDULE_KINDS = ("cron", "interval", "once")
SCHEDULE_KIND_PATTERN = r"^(cron|interval|once)$"
# Guardrail posture a run gets. `write` is the danger-zone case (unattended write).
TOOLS_VALUES = ("read", "write")
TOOLS_PATTERN = r"^(read|write)$"

SCHEDULE_NAME_MAX = 120
SCHEDULE_SPEC_MAX = 120
SCHEDULE_PROMPT_MAX = 8192


class ScheduleCreate(BaseModel):
    name: str = Field(min_length=1, max_length=SCHEDULE_NAME_MAX)
    kind: str = Field(pattern=SCHEDULE_KIND_PATTERN)
    spec: str = Field(min_length=1, max_length=SCHEDULE_SPEC_MAX)
    prompt: str = Field(min_length=1, max_length=SCHEDULE_PROMPT_MAX)
    tools: str = Field(default="read", pattern=TOOLS_PATTERN)
    enabled: bool = True


class ScheduleUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=SCHEDULE_NAME_MAX)
    # kind + spec are validated together; sending one re-validates the pair.
    kind: str | None = Field(default=None, pattern=SCHEDULE_KIND_PATTERN)
    spec: str | None = Field(default=None, min_length=1, max_length=SCHEDULE_SPEC_MAX)
    prompt: str | None = Field(default=None, min_length=1, max_length=SCHEDULE_PROMPT_MAX)
    tools: str | None = Field(default=None, pattern=TOOLS_PATTERN)
    enabled: bool | None = None


class ScheduleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int
    agent_slug: str
    name: str
    kind: str
    spec: str
    prompt: str
    tools: str
    enabled: bool
    next_run_at: datetime | None
    last_run_at: datetime | None
    last_status: str | None
    created_by: str
    created_at: datetime
    updated_at: datetime
