from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="STUDYPILOT_",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "StudyPilot"
    environment: str = "development"
    api_prefix: str = "/api/v1"
    enable_docs: bool = True
    database_url: str = "postgresql+asyncpg://studypilot:studypilot@localhost:5432/studypilot"
    redis_url: str = "redis://localhost:6379/0"
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "course_materials_v1"
    upload_dir: str = "./data/uploads"
    max_upload_mb: int = Field(default=30, ge=1, le=200)
    worker_poll_seconds: float = Field(default=2.0, ge=0.2, le=60)
    development_user_id: str = "00000000-0000-0000-0000-000000000001"


@lru_cache
def get_settings() -> Settings:
    return Settings()
