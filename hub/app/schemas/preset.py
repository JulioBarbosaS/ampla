from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.schemas.agent import SLUG_PATTERN, _clean_denied_paths


class PresetSettings(BaseModel):
    """The guardrail/auto subset a preset carries (Epic 04 · 4.1). Applying copies
    these onto the agent. allowed_senders/auto_schedule stay per-agent."""

    mode: str = Field(default="inbox", pattern=r"^(inbox|auto)$")
    max_auto_per_hour: int = Field(default=10, ge=1, le=120)
    auto_timeout_secs: int = Field(default=120, ge=10, le=600)
    allow_write: bool = False
    block_hidden_files: bool = True
    block_sensitive_paths: bool = True
    confine_to_dir: bool = True
    denied_paths: list[str] = Field(default_factory=list)
    trusted_senders: list[str] = Field(default_factory=list)
    require_approval: bool = False
    auto_paused: bool = False
    max_auto_tokens_per_day: int | None = Field(default=None, ge=1)
    max_auto_cost_usd_per_day: float | None = Field(default=None, ge=0)

    @field_validator("denied_paths")
    @classmethod
    def _check_denied_paths(cls, v: list[str]) -> list[str]:
        return _clean_denied_paths(v)

    @field_validator("trusted_senders")
    @classmethod
    def _check_trusted(cls, v: list[str]) -> list[str]:
        import re

        if any(not re.fullmatch(SLUG_PATTERN, s) for s in v):
            raise ValueError("Slug inválido em trusted_senders.")
        return v


class PresetCreate(BaseModel):
    name: str = Field(min_length=1, max_length=60)
    settings: PresetSettings


class PresetUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=60)
    settings: PresetSettings | None = None


class ApplyPreset(BaseModel):
    preset_id: int


class PresetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner_id: int | None  # null = built-in
    name: str
    settings: PresetSettings
    created_at: datetime


# Built-in presets seeded at startup (matching the danger tiers).
BUILTIN_PRESETS: list[tuple[str, dict]] = [
    ("Estrito (padrão)", PresetSettings().model_dump()),
    ("Leitura ampla", PresetSettings(confine_to_dir=False).model_dump()),
    ("Escrita confinada", PresetSettings(allow_write=True).model_dump()),
    (
        "Confiável (perigo)",
        PresetSettings(
            allow_write=True,
            block_hidden_files=False,
            block_sensitive_paths=False,
            confine_to_dir=False,
        ).model_dump(),
    ),
]
