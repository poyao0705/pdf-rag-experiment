from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[1]
STATIC_DIR = API_ROOT / "static"


class Settings(BaseSettings):
    LOG_LEVEL: str = "INFO"
    THESYS_API_KEY: SecretStr
    THESYS_BASE_URL: str = "https://api.thesys.dev/v1/embed"
    OPENUI_MODEL: str = "google/gemini-3.6-flash-free"
    OPENUI_SPEC_PATH: Path = API_ROOT.parent / "web/src/generated/spec.json"

    @field_validator("THESYS_API_KEY")
    @classmethod
    def validate_secret_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Secret key must not be blank")
        return value

    @field_validator("OPENUI_SPEC_PATH")
    @classmethod
    def resolve_spec_path(cls, value: Path) -> Path:
        return (API_ROOT / value).resolve()

    model_config = SettingsConfigDict(
        env_file=API_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
