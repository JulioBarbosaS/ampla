from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_DENIED_PATHS = 50
MAX_DENIED_PATH_LEN = 200


def _clean_denied_paths(value: list[str]) -> list[str]:
    cleaned = [p.strip() for p in value if p.strip()]
    if len(cleaned) > MAX_DENIED_PATHS:
        raise ValueError(f"No máximo {MAX_DENIED_PATHS} caminhos negados.")
    if any(len(p) > MAX_DENIED_PATH_LEN for p in cleaned):
        raise ValueError(f"Cada caminho negado deve ter até {MAX_DENIED_PATH_LEN} caracteres.")
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

    @field_validator("denied_paths")
    @classmethod
    def _check_denied_paths(cls, v: list[str] | None) -> list[str] | None:
        return None if v is None else _clean_denied_paths(v)


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
