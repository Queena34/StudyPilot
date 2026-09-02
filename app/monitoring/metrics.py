"""Prometheus metrics for user-visible StudyPilot behaviour.

Labels are deliberately bounded enums or code-owned names. User, course,
document and trace identifiers never become labels: they belong in logs and
traces, not in a time-series cardinality explosion.
"""

from prometheus_client import Counter, Histogram

from app.agents.protocol import AgentResult, AgentTrace


HTTP_REQUESTS = Counter(
    "studypilot_http_requests_total",
    "HTTP requests handled by the application.",
    ("method", "route", "status_class"),
)
HTTP_LATENCY = Histogram(
    "studypilot_http_request_duration_seconds",
    "HTTP request duration in seconds.",
    ("method", "route"),
)
ROUTER_DECISIONS = Counter(
    "studypilot_router_decisions_total",
    "Final routing decisions by source, intent, target and execution mode.",
    ("source", "intent", "target", "execution_mode"),
)
WORKFLOWS = Counter(
    "studypilot_workflows_total",
    "Learning workflows by execution mode and final status.",
    ("execution_mode", "status"),
)
WORKFLOW_LATENCY = Histogram(
    "studypilot_workflow_duration_seconds",
    "End-to-end orchestrator duration in seconds.",
    ("execution_mode",),
)
AGENT_STEPS = Counter(
    "studypilot_agent_steps_total",
    "Agent steps by agent, role and outcome.",
    ("agent", "role", "status"),
)
AGENT_LATENCY = Histogram(
    "studypilot_agent_step_duration_seconds",
    "Agent step duration in seconds.",
    ("agent", "role"),
)
TOOL_CALLS = Counter(
    "studypilot_tool_calls_total",
    "Teaching tool calls by tool and outcome.",
    ("tool", "outcome"),
)
TOOL_LATENCY = Histogram(
    "studypilot_tool_call_duration_seconds",
    "Teaching tool duration in seconds.",
    ("tool",),
)
TUTOR_RESULTS = Counter(
    "studypilot_tutor_results_total",
    "Tutor turns by evidence and fallback outcome.",
    ("evidence_status", "fallback_reason"),
)
LLM_TOKENS = Counter(
    "studypilot_llm_tokens_total",
    "Tokens reported for final tutor generation by model and direction.",
    ("model", "direction"),
)


def _seconds(milliseconds: int | float) -> float:
    return max(0.0, float(milliseconds) / 1000.0)


def observe_http_request(method: str, route: str, status_code: int, elapsed: float) -> None:
    status_class = f"{status_code // 100}xx"
    HTTP_REQUESTS.labels(method=method, route=route, status_class=status_class).inc()
    HTTP_LATENCY.labels(method=method, route=route).observe(max(0.0, elapsed))


def observe_trace(trace: AgentTrace, final_status: str) -> None:
    route = trace.route
    source = str(route.get("source", "unknown"))
    intent = str(route.get("intent", "unknown"))
    target = str(route.get("target", "unknown"))
    execution_mode = str(route.get("execution_mode", "unknown"))
    ROUTER_DECISIONS.labels(
        source=source,
        intent=intent,
        target=target,
        execution_mode=execution_mode,
    ).inc()
    WORKFLOWS.labels(execution_mode=execution_mode, status=final_status).inc()
    WORKFLOW_LATENCY.labels(execution_mode=execution_mode).observe(
        _seconds(trace.total_latency_ms)
    )
    for step in trace.steps:
        AGENT_STEPS.labels(
            agent=step.agent.value,
            role=step.role,
            status=step.status.value,
        ).inc()
        AGENT_LATENCY.labels(agent=step.agent.value, role=step.role).observe(
            _seconds(step.latency_ms)
        )
        for call in step.tool_calls:
            outcome = "success" if call.ok else "failure"
            TOOL_CALLS.labels(tool=call.name, outcome=outcome).inc()
            TOOL_LATENCY.labels(tool=call.name).observe(_seconds(call.latency_ms))


def observe_tutor_result(result: AgentResult) -> None:
    fallback = result.fallback_reason or "none"
    TUTOR_RESULTS.labels(
        evidence_status=result.evidence_status,
        fallback_reason=fallback,
    ).inc()
    model = result.model_name or "unknown"
    if result.input_tokens is not None:
        LLM_TOKENS.labels(model=model, direction="input").inc(result.input_tokens)
    if result.output_tokens is not None:
        LLM_TOKENS.labels(model=model, direction="output").inc(result.output_tokens)
