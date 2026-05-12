from __future__ import annotations

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


_MODEL_DEFAULTS: dict[str, str] = {
    "claude": "claude-3-5-sonnet-20241022",
    "openai": "gpt-4o",
    "mistral": "mistral-large-latest",
}


class LLMConfig(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    provider: str = Field(default="claude", alias="LLM_PROVIDER")
    model: str = Field(default="", alias="LLM_MODEL")
    max_tokens: int = Field(default=2000, alias="LLM_MAX_TOKENS")
    temperature_generation: float = Field(default=0.5, alias="LLM_TEMPERATURE_GENERATION")
    temperature_toolcall: float = Field(default=0.1, alias="LLM_TEMPERATURE_TOOLCALL")

    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    mistral_api_key: str = Field(default="", alias="MISTRAL_API_KEY")

    @model_validator(mode="after")
    def set_default_model(self) -> "LLMConfig":
        if not self.model:
            self.model = _MODEL_DEFAULTS.get(self.provider, "claude-3-5-sonnet-20241022")
        return self
