from functools import lru_cache
from pathlib import Path

from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    LOG_LEVEL: str = "INFO"
    # OPENAI_API_KEY: SecretStr
    THESYS_API_KEY: SecretStr

    @field_validator("THESYS_API_KEY")
    def validate_secret_key(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("Secret key must not be blank")
        return value

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore


API_ROOT: Path = Path(__file__).resolve().parents[1]
STATIC_DIR = API_ROOT / "static"
