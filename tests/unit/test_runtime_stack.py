from pathlib import Path

from app.core.config import Settings


ROOT = Path(__file__).resolve().parents[2]


def test_redis_is_not_application_configuration() -> None:
    assert "redis_url" not in Settings.model_fields


def test_redis_is_not_a_deployment_dependency() -> None:
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")

    assert "\n  redis:" not in compose
    assert "STUDYPILOT_REDIS_URL" not in compose
    assert not any(
        line.strip().lower().startswith("redis==")
        for line in requirements.splitlines()
    )
