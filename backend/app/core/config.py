from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "TJGO CAPFI Cloud"
    api_v1_prefix: str = ""
    debug: bool = False
    database_url: str = Field(..., alias="DATABASE_URL")
    secret_key: str = Field(..., alias="SECRET_KEY")
    access_token_expire_days: int = 7
    algorithm: str = "HS256"

    redis_url: str | None = Field(default=None, alias="REDIS_URL")
    rq_queue_name: str = "tjgo-capfi-jobs"
    admin_registration_key: str | None = Field(default=None, alias="ADMIN_REGISTRATION_KEY")

    projudi_user: str = Field(..., alias="PROJUDI_USER")
    projudi_password: str = Field(..., alias="PROJUDI_PASSWORD")
    projudi_base_url: str = "https://projudi.tjgo.jus.br/BuscaProcesso?PaginaAtual=4"
    projudi_login_selector: str = 'input[name="login"], #login, #username'
    projudi_password_selector: str = 'input[name="senha"], input[type="password"], #password'
    projudi_submit_selector: str = 'button[type="submit"], input[type="submit"], #btnEntrar'

    cors_allow_origins: list[str] = ["*"]
    cors_allow_methods: list[str] = ["*"]
    cors_allow_headers: list[str] = ["*"]

    upload_dir: Path = Path("/tmp/uploads")
    result_dir: Path = Path("/tmp/results")
    job_timeout_seconds: int = 60 * 30


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    settings.result_dir.mkdir(parents=True, exist_ok=True)
    return settings
