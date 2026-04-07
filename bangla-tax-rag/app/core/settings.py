from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = Field(default="bangla-tax-rag", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    config_path: str = Field(default="config/config.dev.yaml", alias="CONFIG_PATH")

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    def load_yaml_config(self) -> dict:
        config_file = Path(self.config_path)
        if not config_file.exists():
            return {}
        with config_file.open("r", encoding="utf-8") as handle:
            return yaml.safe_load(handle) or {}


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
