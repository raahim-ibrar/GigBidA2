from pathlib import Path

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    app_env: str = "development"
    web_origin: str = "http://localhost:3000"
    marketplace_mode: str = "gigsim"
    student_sim_url: str = "http://127.0.0.1:8080"
    student_sim_api_key: str = "student_sim_local_only"
    database_url: str = "postgresql+psycopg://gigbid:gigbid_local_only@127.0.0.1:5432/gigbid"
    session_cookie_name: str = "gigbid_session"
    session_lifetime_hours: int = Field(default=168, ge=1, le=720)
    cookie_secure: bool = False
    redis_url: str = "redis://127.0.0.1:6379/0"
    qdrant_url: str = "http://127.0.0.1:6333"
    ollama_base_url: str = "http://127.0.0.1:11434"
    groq_api_key: SecretStr = Field(default=SecretStr(""), repr=False)
    model_cache_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "work/models"
    )
    max_portfolio_upload_bytes: int = 10 * 1024 * 1024

    @model_validator(mode="after")
    def production_cookies(self):
        if self.app_env == "production" and (
            not self.cookie_secure or not self.web_origin.startswith("https://")
        ):
            raise ValueError("Production requires HTTPS and Secure session cookies")
        return self
