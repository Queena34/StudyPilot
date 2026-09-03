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
    chroma_host: str = "localhost"
    chroma_port: int = 8001
    chroma_collection: str = "course_materials_v2"
    upload_dir: str = "./data/uploads"
    max_upload_mb: int = Field(default=30, ge=1, le=200)
    worker_poll_seconds: float = Field(default=2.0, ge=0.2, le=60)
    #: A worker that dies mid-job leaves it marked running forever, and nothing
    #: reclaims it: only queued jobs are picked up. The lease has to outlast the
    #: slowest real ingestion — a 100-page PDF takes minutes to embed — so a
    #: healthy worker is never robbed of a job it is still working on.
    job_lease_seconds: float = Field(default=1800.0, ge=60, le=86400)
    #: A job that stalls repeatedly is failing, not unlucky. Failing it surfaces
    #: the problem to the learner, who can retry, instead of looping forever.
    job_max_attempts: int = Field(default=3, ge=1, le=10)
    anthropic_api_key: str | None = None
    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_model: str = "claude-3-5-sonnet-20241022"
    llm_timeout_seconds: float = Field(default=45, ge=5, le=180)
    development_user_id: str = "00000000-0000-0000-0000-000000000001"


@lru_cache
def get_settings() -> Settings:
    return Settings()
