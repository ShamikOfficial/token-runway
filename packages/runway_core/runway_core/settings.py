"""App settings — reads env the way a human would name things."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Repo root: packages/runway_core/runway_core/settings.py -> up 3
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    runway_env: str = "local"
    aws_endpoint_url: str | None = "http://localhost:4566"
    aws_access_key_id: str = "test"
    aws_secret_access_key: str = "test"
    aws_default_region: str = "us-east-1"

    runway_budgets_table: str = "tokenrunway-budgets"
    runway_usage_table: str = "tokenrunway-usage"
    runway_raw_bucket: str = "tokenrunway-raw"

    runway_pricing_overrides: str = str(_REPO_ROOT / "samples" / "pricing_overrides.json")
    runway_ewma_alpha: float = 0.3
    runway_bingo_reserve_pct: float = 0.10

    @property
    def using_floci(self) -> bool:
        return bool(self.aws_endpoint_url) and self.runway_env == "local"

    @property
    def pricing_overrides_path(self) -> Path:
        path = Path(self.runway_pricing_overrides)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
