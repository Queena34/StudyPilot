from uuid import UUID
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import Response
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.agents.protocol import AgentResult, AgentStatus, AgentStep, AgentTrace, ToolCall
from app.agents.routing import AgentName
from app.main import app
from app.monitoring.metrics import observe_trace, observe_tutor_result
from app.api.v1.routes.tutor import create_tutor_message
from app.schemas.tutor import TutorMessageCreate
from app.services.tutor_service import TutorService


def _value(name: str, labels: dict[str, str]) -> float:
    return REGISTRY.get_sample_value(name, labels) or 0.0


def test_http_metrics_use_the_route_template_and_return_request_id() -> None:
    client = TestClient(app)
    labels = {"method": "GET", "route": "/", "status_class": "2xx"}
    before = _value("studypilot_http_requests_total", labels)

    response = client.get("/", headers={"x-request-id": "monitoring-test"})

    assert response.headers["x-request-id"] == "monitoring-test"
    assert _value("studypilot_http_requests_total", labels) == before + 1


def test_metrics_endpoint_exposes_business_metric_names() -> None:
    body = TestClient(app).get("/api/v1/metrics").text

    for name in (
        "studypilot_http_requests_total",
        "studypilot_router_decisions_total",
        "studypilot_workflows_total",
        "studypilot_agent_steps_total",
        "studypilot_tool_calls_total",
        "studypilot_tutor_results_total",
        "studypilot_llm_tokens_total",
    ):
        assert name in body


def test_trace_observation_records_route_agent_tool_and_workflow() -> None:
    trace = AgentTrace(
        trace_id=UUID("00000000-0000-0000-0000-000000000123"),
        route={
            "source": "rule",
            "intent": "course_qa",
            "target": "rag",
            "execution_mode": "single",
        },
        steps=[
            AgentStep(
                agent=AgentName.TUTOR,
                role="primary",
                status=AgentStatus.OK,
                latency_ms=12,
                model_name="test-model",
                tool_calls=[ToolCall("search_course_material", True, 4)],
            )
        ],
        total_latency_ms=15,
    )
    route_labels = {
        "source": "rule",
        "intent": "course_qa",
        "target": "rag",
        "execution_mode": "single",
    }
    before = _value("studypilot_router_decisions_total", route_labels)

    observe_trace(trace, "ok")

    assert _value("studypilot_router_decisions_total", route_labels) == before + 1
    assert _value(
        "studypilot_agent_steps_total",
        {"agent": "tutor", "role": "primary", "status": "ok"},
    ) >= 1
    assert _value(
        "studypilot_tool_calls_total",
        {"tool": "search_course_material", "outcome": "success"},
    ) >= 1


def test_tutor_result_records_quality_outcome_and_tokens() -> None:
    result = AgentResult(
        answer="answer",
        evidence_status="sufficient",
        model_name="metrics-test-model",
        input_tokens=12,
        output_tokens=7,
        fallback_reason=None,
    )
    labels = {"evidence_status": "sufficient", "fallback_reason": "none"}
    before = _value("studypilot_tutor_results_total", labels)

    observe_tutor_result(result)

    assert _value("studypilot_tutor_results_total", labels) == before + 1
    assert _value(
        "studypilot_llm_tokens_total",
        {"model": "metrics-test-model", "direction": "input"},
    ) >= 12
    assert _value(
        "studypilot_llm_tokens_total",
        {"model": "metrics-test-model", "direction": "output"},
    ) >= 7


@pytest.mark.asyncio
async def test_tutor_endpoint_returns_the_agent_trace_id(monkeypatch) -> None:
    trace_id = "00000000-0000-0000-0000-000000000456"
    answer = SimpleNamespace(trace={"trace_id": trace_id})
    monkeypatch.setattr(TutorService, "answer", AsyncMock(return_value=answer))
    response = Response()

    result = await create_tutor_message(
        course_id=UUID("00000000-0000-0000-0000-000000000010"),
        body=TutorMessageCreate(message="解释残差"),
        session=object(),
        user_id=UUID("00000000-0000-0000-0000-000000000011"),
        response=response,
    )

    assert result is answer
    assert response.headers["x-trace-id"] == trace_id
