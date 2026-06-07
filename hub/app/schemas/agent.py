from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

# Slug público do agente (docs/ARCHITECTURE.md · Segurança · Transversal)
SLUG_PATTERN = r"^[a-z][a-z0-9-]{1,48}[a-z0-9]$"

# Slugs reservados — não podem ser usados por agente nem por grupo.
# "all" é o broadcast virtual (@all). Namespace compartilhado agente↔grupo.
RESERVED_SLUGS = {"all"}


class AgentSettings(BaseModel):
    """Settings do agente — espelhadas em bridge/src/shared/protocol.ts."""

    model_config = ConfigDict(from_attributes=True)

    mode: str = Field(default="inbox", pattern=r"^(inbox|auto)$")
    allowed_senders: list[str] | None = None  # None = todos podem enviar
    max_auto_per_hour: int = Field(default=10, ge=1, le=120)
    auto_timeout_secs: int = Field(default=120, ge=10, le=600)
    instructions: str = Field(default="", max_length=4000)


class AgentSettingsUpdate(BaseModel):
    """PATCH parcial — apenas campos presentes são alterados."""

    mode: str | None = Field(default=None, pattern=r"^(inbox|auto)$")
    allowed_senders: list[str] | None = None
    clear_allowed_senders: bool = False  # allowed_senders=None no PATCH é ambíguo
    max_auto_per_hour: int | None = Field(default=None, ge=1, le=120)
    auto_timeout_secs: int | None = Field(default=None, ge=10, le=600)
    instructions: str | None = Field(default=None, max_length=4000)


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


class DirectoryEntry(BaseModel):
    """Visão pública de um agente para o diretório da equipe."""

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
    """Resposta da criação — única vez que a chave aparece em plaintext."""

    id: int
    label: str
    key: str


class AgentKeyCreate(BaseModel):
    label: str = Field(default="", max_length=120)
