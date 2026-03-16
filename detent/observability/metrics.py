# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Detent Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Metric instrument registry for Detent."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from detent.config import TelemetryConfig

logger = logging.getLogger(__name__)

_meter_provider: Any | None = None
_meter: Any | None = None
_tool_calls_counter: Any | None = None
_pipeline_duration_histogram: Any | None = None
_stage_duration_histogram: Any | None = None
_stage_findings_histogram: Any | None = None
_savepoint_size_histogram: Any | None = None
_rollback_counter: Any | None = None
_proxy_request_histogram: Any | None = None
_proxy_retries_counter: Any | None = None
_circuit_breaker_trips_counter: Any | None = None
_circuit_breaker_state_instrument: Any | None = None
_circuit_states: dict[str, int] = {}


def configure_metrics(config: TelemetryConfig, exporter: Any) -> None:
    """Register metric instruments and exporters."""
    global _meter_provider, _meter

    if _meter_provider is not None:
        return

    try:
        from opentelemetry import metrics
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
    except ImportError as exc:
        raise ImportError("OpenTelemetry SDK not installed. Run: pip install detent[telemetry]") from exc

    reader = PeriodicExportingMetricReader(exporter)
    provider = MeterProvider(metric_readers=[reader])
    metrics.set_meter_provider(provider)
    meter = provider.get_meter("detent")

    _register_instruments(meter)

    _meter_provider = provider
    _meter = meter


def _register_instruments(meter: Any) -> None:
    global _tool_calls_counter
    global _pipeline_duration_histogram
    global _stage_duration_histogram
    global _stage_findings_histogram
    global _savepoint_size_histogram
    global _rollback_counter
    global _proxy_request_histogram
    global _proxy_retries_counter
    global _circuit_breaker_trips_counter
    global _circuit_breaker_state_instrument

    _tool_calls_counter = meter.create_counter("detent.tool_calls.total", unit="1")
    _pipeline_duration_histogram = meter.create_histogram("detent.pipeline.duration", unit="ms")
    _stage_duration_histogram = meter.create_histogram("detent.stage.duration", unit="ms")
    _stage_findings_histogram = meter.create_histogram("detent.stage.findings", unit="1")
    _savepoint_size_histogram = meter.create_histogram("detent.checkpoint.savepoint_size", unit="1")
    _rollback_counter = meter.create_counter("detent.rollbacks.total", unit="1")
    _proxy_request_histogram = meter.create_histogram("detent.proxy.request.duration", unit="ms")
    _proxy_retries_counter = meter.create_counter("detent.proxy.retries", unit="1")
    _circuit_breaker_trips_counter = meter.create_counter("detent.circuit_breaker.trips", unit="1")
    _circuit_breaker_state_instrument = meter.create_observable_gauge(
        "detent.circuit_breaker.state",
        callbacks=[_circuit_state_callback],
        unit="1",
    )


def _circuit_state_callback(_: Any) -> list[Any]:
    try:
        from opentelemetry.metrics import Observation
    except ImportError:
        return []

    return [Observation(state, {"component": component}) for component, state in _circuit_states.items()]


def _format_bool(value: bool) -> str:
    return "true" if value else "false"


def record_tool_call(agent: str, action_type: str, passed: bool) -> None:
    if _tool_calls_counter is None:
        return
    _tool_calls_counter.add(
        1,
        {"agent": agent, "action_type": action_type, "passed": _format_bool(passed)},
    )


def record_pipeline_duration(language: str, passed: bool, duration_ms: float) -> None:
    if _pipeline_duration_histogram is None:
        return
    _pipeline_duration_histogram.record(
        duration_ms,
        {"language": language, "passed": _format_bool(passed)},
    )


def record_stage_duration(stage_name: str, language: str, passed: bool, duration_ms: float) -> None:
    if _stage_duration_histogram is None:
        return
    _stage_duration_histogram.record(
        duration_ms,
        {
            "stage_name": stage_name,
            "language": language,
            "passed": _format_bool(passed),
        },
    )


def record_stage_findings(stage_name: str, severity: str) -> None:
    if _stage_findings_histogram is None:
        return
    _stage_findings_histogram.record(
        1,
        {"stage_name": stage_name, "severity": severity},
    )


def record_savepoint_size(file_count: int) -> None:
    if _savepoint_size_histogram is None:
        return
    _savepoint_size_histogram.record(file_count, {"file_count": file_count})


def record_rollback(triggered_by_stage: str) -> None:
    if _rollback_counter is None:
        return
    _rollback_counter.add(1, {"triggered_by_stage": triggered_by_stage})


def record_proxy_request(upstream_host: str, status_code: int, duration_ms: float) -> None:
    if _proxy_request_histogram is None:
        return
    _proxy_request_histogram.record(
        duration_ms,
        {"upstream_host": upstream_host, "status_code": str(status_code)},
    )


def record_proxy_retry(upstream_host: str, attempt: int) -> None:
    if _proxy_retries_counter is None:
        return
    _proxy_retries_counter.add(
        1,
        {"upstream_host": upstream_host, "attempt": str(attempt)},
    )


def increment_circuit_breaker_trip(component: str) -> None:
    if _circuit_breaker_trips_counter is None:
        return
    _circuit_breaker_trips_counter.add(1, {"component": component})


def update_circuit_breaker_state(component: str, state_value: int) -> None:
    _circuit_states[component] = state_value
