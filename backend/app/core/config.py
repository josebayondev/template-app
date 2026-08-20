import os
from functools import lru_cache
from typing import Annotated, Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

# The dotenv file is a local-development convenience: Render and Docker inject real
# environment variables and ship no .env at all. Making the path itself overridable is
# what lets the test suite opt out of it entirely -- tests/conftest.py sets ENV_FILE to
# an empty string, which means "read no file", so Settings falls back to the defaults
# below instead of to whatever database the developer happens to have configured.
_ENV_FILE = os.getenv("ENV_FILE", ".env") or None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=_ENV_FILE, extra="ignore")

    environment: Literal["local", "preview", "production"] = "local"
    project_name: str = "MyApp API"
    # NoDecode is required: without it pydantic-settings tries to JSON-decode the
    # raw value before any validator runs, so a comma-separated CORS_ORIGINS
    # raises SettingsError at startup and split_cors_origins never gets called.
    # Defaults to no origins at all: a deployment that forgets CORS_ORIGINS must
    # fail closed, not silently allow a developer's localhost. Local setups get the
    # origin from .env.example or docker-compose.yml, where it is spelled out.
    cors_origins: Annotated[list[str], NoDecode] = []
    database_url: str = "postgresql://postgres:postgres@localhost:5432/myapp"
    # Unset means "Sentry off": that is the default locally and in CI, and only
    # the deployed environments define it.
    sentry_dsn: str | None = None

    @field_validator("cors_origins", mode="before")
    @classmethod
    def split_cors_origins(cls, value: str | list[str]) -> str | list[str]:
        if isinstance(value, str):
            return [origin.strip() for origin in value.split(",") if origin.strip()]
        return value


@lru_cache
def get_settings() -> Settings:
    return Settings()
