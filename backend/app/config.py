from typing import Literal

from pydantic import AliasChoices, Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    environment: Literal["development", "test", "production"] = "development"
    database_url: str = "sqlite:///./graded_reader.db"
    jwt_secret: str = "development-secret-change-me-please"
    generation_provider_url: str | None = None
    generation_provider_token: str | None = None
    openai_api_key: str | None = Field(default=None, validation_alias=AliasChoices("OPENAI_API_KEY", "KICONNECT_API_KEY"))
    model_provider: Literal["openai", "kiconnect"] = Field(default="openai", validation_alias=AliasChoices("MODEL_PROVIDER", "GENERATION_MODEL_PROVIDER"))
    model_base_url: str | None = Field(default=None, validation_alias=AliasChoices("BASE_URL", "OPENAI_BASE_URL", "GENERATION_BASE_URL"))
    generation_default_model: str = "GPT5-mini-Studierende"
    generation_timeout_seconds: float = 120.0
    korean_dictionary_api_key: str | None = Field(default=None, validation_alias=AliasChoices("KOREAN_DICTIONARY_API_KEY", "OPENDICT_API_KEY"))
    korean_dictionary_url: str = "https://krdict.korean.go.kr/api/search"
    dictionary_timeout_seconds: float = 20.0
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @model_validator(mode="after")
    def validate_runtime_configuration(self) -> "Settings":
        if bool(self.generation_provider_url) != bool(self.generation_provider_token):
            raise ValueError("GENERATION_PROVIDER_URL and GENERATION_PROVIDER_TOKEN must be set together")
        if self.model_provider == "kiconnect" and not self.openai_api_key:
            raise ValueError("KICONNECT_API_KEY or OPENAI_API_KEY must be set when MODEL_PROVIDER=kiconnect")
        if self.environment == "production" and self.jwt_secret == "development-secret-change-me-please":
            raise ValueError("JWT_SECRET must be changed in production")
        return self

    @property
    def openai_responses_base_url(self) -> str:
        if self.model_base_url:
            return self.model_base_url
        if self.model_provider == "kiconnect":
            return "https://chat.kiconnect.nrw/api/v1"
        return "https://api.openai.com/v1"


settings = Settings()
