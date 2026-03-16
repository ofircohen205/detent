"""Integration test for OpenTelemetry spans emitted by the pipeline."""

import pytest

try:
    from opentelemetry.sdk.trace.export import InMemorySpanExporter
except ImportError:  # pragma: no cover - fallback for newer opentelemetry
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from detent.config import PipelineConfig, StageConfig, TelemetryConfig
from detent.observability import setup_telemetry
from detent.observability.exporter import ExporterBundle, NoOpMetricExporter
from detent.observability.tracer import get_tracer
from detent.pipeline.pipeline import VerificationPipeline
from detent.pipeline.result import VerificationResult
from detent.schema import ActionType, AgentAction, RiskLevel
from detent.stages.base import VerificationStage


class DummyStage(VerificationStage):
    name = "dummy"

    async def _run(self, action: AgentAction) -> VerificationResult:
        return VerificationResult(stage="dummy", passed=True, findings=[], duration_ms=1.0)


@pytest.mark.asyncio
async def test_pipeline_emits_spans(monkeypatch):
    bundle = ExporterBundle(
        span_exporter=InMemorySpanExporter(),
        metric_exporter=NoOpMetricExporter(),
    )

    monkeypatch.setattr("detent.observability.build_exporter", lambda cfg: bundle)
    monkeypatch.setattr("detent.observability._initialized", False)
    monkeypatch.setattr("detent.observability.tracer._configured", False)
    monkeypatch.setattr("detent.observability.metrics._meter_provider", None)
    monkeypatch.setattr("detent.observability.metrics._meter", None)

    setup_telemetry(TelemetryConfig(enabled=True))

    tracer = get_tracer(__name__)
    pipeline = VerificationPipeline(
        stages=[DummyStage(StageConfig(name="dummy", enabled=True))],
        config=PipelineConfig(parallel=False, fail_fast=True),
    )

    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="integration",
        tool_name="Write",
        tool_input={"file_path": "/tmp/test.py", "content": "print('hello')"},
        tool_call_id="tool_123",
        session_id="sess_123",
        checkpoint_ref="chk_000",
        risk_level=RiskLevel.MEDIUM,
    )

    with tracer.start_as_current_span(
        "detent.tool_call",
        attributes={"detent.file_path": "/tmp/test.py", "detent.session_id": "sess_123"},
    ):
        await pipeline.run(action)

    try:
        from opentelemetry import trace

        trace.get_tracer_provider().force_flush()
    except Exception:
        pass

    spans = bundle.span_exporter.get_finished_spans()
    names = {span.name for span in spans}
    assert {"detent.tool_call", "detent.pipeline", "detent.stage.dummy"} <= names
