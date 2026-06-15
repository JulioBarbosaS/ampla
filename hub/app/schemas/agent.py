from datetime import datetime
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

MAX_DENIED_PATHS = 50
MAX_DENIED_PATH_LEN = 200

# Availability schedule (Epic 04 · 4.2)
_HHMM_PATTERN = r"^([01]\d|2[0-3]):[0-5]\d$"
MAX_SCHEDULE_WINDOWS = 14


class ScheduleWindow(BaseModel):
    """One recurring availability window. days are ISO weekdays (1=Mon..7=Sun);
    start/end are HH:MM in the schedule's timezone, same-day (start < end)."""

    days: list[int] = Field(min_length=1, max_length=7)
    start: str = Field(pattern=_HHMM_PATTERN)
    end: str = Field(pattern=_HHMM_PATTERN)

    @field_validator("days")
    @classmethod
    def _check_days(cls, v: list[int]) -> list[int]:
        if any(d < 1 or d > 7 for d in v):
            raise ValueError("days devem estar entre 1 (seg) e 7 (dom).")
        return sorted(set(v))

    @model_validator(mode="after")
    def _check_order(self) -> "ScheduleWindow":
        if self.start >= self.end:
            raise ValueError("start deve ser antes de end (mesmo dia, HH:MM).")
        return self


class AutoSchedule(BaseModel):
    """Auto-respond availability: only inside these windows, in `tz`."""

    tz: str = Field(min_length=1, max_length=64)
    windows: list[ScheduleWindow] = Field(min_length=1, max_length=MAX_SCHEDULE_WINDOWS)

    @field_validator("tz")
    @classmethod
    def _check_tz(cls, v: str) -> str:
        try:
            ZoneInfo(v)
        except Exception:  # noqa: BLE001 — any failure = not a valid IANA tz
            raise ValueError("Timezone IANA inválida.") from None
        return v


def _clean_denied_paths(value: list[str]) -> list[str]:
    cleaned = [p.strip() for p in value if p.strip()]
    if len(cleaned) > MAX_DENIED_PATHS:
        raise ValueError(f"No máximo {MAX_DENIED_PATHS} caminhos negados.")
    if any(len(p) > MAX_DENIED_PATH_LEN for p in cleaned):
        raise ValueError(f"Cada caminho negado deve ter até {MAX_DENIED_PATH_LEN} caracteres.")
    return cleaned


# Escalation outcomes (Epic 04 · 4.3) — the auto-respond results the owner may
# route to their Inbox. These mirror the daemon's reported result/reason: a
# `failed`/`blocked` run, or a `skipped` run whose reason is one of these. The
# model's explicit `__ESCALATE__` sentinel always escalates and is therefore NOT
# user-configurable (not listed here).
ESCALATE_OUTCOMES = ("failed", "blocked", "rate_limited", "budget_exceeded", "outside_hours")


def _clean_escalate_on(value: list[str]) -> list[str]:
    cleaned: list[str] = []
    for item in value:
        if item not in ESCALATE_OUTCOMES:
            raise ValueError(f"Outcome de escalação inválido: {item!r}.")
        if item not in cleaned:
            cleaned.append(item)
    return cleaned


# Public agent slug (docs/ARCHITECTURE.md · Security · Cross-cutting)
SLUG_PATTERN = r"^[a-z][a-z0-9-]{1,48}[a-z0-9]$"

# Reserved slugs — cannot be used by an agent or a group.
# "all" is the virtual broadcast (@all). Namespace shared between agent and group.
RESERVED_SLUGS = {"all"}


class AgentSettings(BaseModel):
    """Agent settings — mirrored in bridge/src/shared/protocol.ts."""

    model_config = ConfigDict(from_attributes=True)

    mode: str = Field(default="inbox", pattern=r"^(inbox|auto)$")
    allowed_senders: list[str] | None = None  # None = everyone can send
    max_auto_per_hour: int = Field(default=10, ge=1, le=120)
    auto_timeout_secs: int = Field(default=120, ge=10, le=600)
    instructions: str = Field(default="", max_length=4000)

    # Auto-respond filesystem guardrails. The daemon turns these into claude -p
    # deny-rules/flags before answering an untrusted sender (Threat 1).
    allow_write: bool = False  # read-only (Read/Grep/Glob) unless enabled (then Edit/Write)
    block_hidden_files: bool = True  # deny dotfiles (.env, .gitignore, ...)
    block_sensitive_paths: bool = True  # deny ~/.ssh, ~/.aws, /etc, ... (danger zone to disable)
    confine_to_dir: bool = True  # no access outside the project dir
    denied_paths: list[str] = Field(default_factory=list)  # extra custom globs to deny
    # Trusted senders bypass ALL of the above — their messages run with full
    # access (write still gated by allow_write).
    trusted_senders: list[str] = Field(default_factory=list)

    # Fast brake (Epic 03 · 3.2): pause auto-respond without changing `mode`.
    # When true the daemon treats the agent as inbox regardless of `mode`.
    auto_paused: bool = False

    # Daily auto-respond budget (Epic 03 · 3.4). None = unlimited. Enforced by the
    # daemon against captured usage (requires capture_usage on the daemon).
    max_auto_tokens_per_day: int | None = Field(default=None, ge=1)
    max_auto_cost_usd_per_day: float | None = Field(default=None, ge=0)

    # Human-in-the-loop approval (Epic 03 · 3.3): draft, don't send, until the
    # owner approves. Only meaningful when mode=auto.
    require_approval: bool = False

    # Availability window / DND (Epic 04 · 4.2): null = always-on.
    auto_schedule: AutoSchedule | None = None

    @field_validator("denied_paths")
    @classmethod
    def _check_denied_paths(cls, v: list[str]) -> list[str]:
        return _clean_denied_paths(v)


class AgentSettingsUpdate(BaseModel):
    """Partial PATCH — only fields that are present get changed."""

    mode: str | None = Field(default=None, pattern=r"^(inbox|auto)$")
    allowed_senders: list[str] | None = None
    clear_allowed_senders: bool = False  # allowed_senders=None in the PATCH is ambiguous
    max_auto_per_hour: int | None = Field(default=None, ge=1, le=120)
    auto_timeout_secs: int | None = Field(default=None, ge=10, le=600)
    instructions: str | None = Field(default=None, max_length=4000)
    allow_write: bool | None = None
    block_hidden_files: bool | None = None
    block_sensitive_paths: bool | None = None
    confine_to_dir: bool | None = None
    denied_paths: list[str] | None = None
    trusted_senders: list[str] | None = None
    auto_paused: bool | None = None
    # Budget caps (Epic 03 · 3.4): None = unchanged; 0 = clear (unlimited);
    # a positive value sets the daily ceiling.
    max_auto_tokens_per_day: int | None = Field(default=None, ge=0)
    max_auto_cost_usd_per_day: float | None = Field(default=None, ge=0)
    require_approval: bool | None = None
    # null = unchanged; set to apply a schedule. clear_auto_schedule wipes it
    # (back to always-on), since null can't mean both "unchanged" and "always".
    auto_schedule: AutoSchedule | None = None
    clear_auto_schedule: bool = False
    # null = unchanged; [] explicitly disables escalation. Values validated
    # against ESCALATE_OUTCOMES (Epic 04 · 4.3).
    escalate_on: list[str] | None = None

    @field_validator("denied_paths")
    @classmethod
    def _check_denied_paths(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _clean_denied_paths(v)

    @field_validator("escalate_on")
    @classmethod
    def _check_escalate_on(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _clean_escalate_on(v)


class AgentCreate(BaseModel):
    slug: str = Field(pattern=SLUG_PATTERN, max_length=50)
    display_name: str = Field(min_length=1, max_length=120)


class AgentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    slug: str
    user_id: int
    display_name: str
    created_at: datetime
    mode: str
    allowed_senders: list[str] | None
    max_auto_per_hour: int
    auto_timeout_secs: int
    instructions: str
    allow_write: bool
    block_hidden_files: bool
    block_sensitive_paths: bool
    confine_to_dir: bool
    denied_paths: list[str]
    trusted_senders: list[str]
    auto_paused: bool
    max_auto_tokens_per_day: int | None
    max_auto_cost_usd_per_day: float | None
    require_approval: bool
    auto_schedule: AutoSchedule | None
    escalate_on: list[str]


class DirectoryEntry(BaseModel):
    """Public view of an agent for the team directory."""

    slug: str
    display_name: str
    online: bool


class AgentKeyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    label: str
    created_at: datetime
    revoked_at: datetime | None


class AgentKeyCreated(BaseModel):
    """Creation response — the only time the key appears in plaintext."""

    id: int
    label: str
    key: str


class AgentKeyCreate(BaseModel):
    label: str = Field(default="", max_length=120)
