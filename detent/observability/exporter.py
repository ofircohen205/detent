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

"""Exporter factory for OpenTelemetry spans and metrics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from detent.observability.schemas import ExporterBundle

if TYPE_CHECKING:
    from detent.config import TelemetryConfig


class NoOpMetricExporter:
    """Metric exporter that drops all data."""

    def __init__(
        self,
        inner: Any | None = None,
        preferred_temporality: dict[type, Any] | None = None,
        preferred_aggregation: dict[type, Any] | None = None,
    ) -> None:
        if inner is None:
            from opentelemetry.sdk.metrics.export import MetricExportResult

            inner = MetricExportResult
        self._inner = inner
        self._preferred_temporality = preferred_temporality
        self._preferred_aggregation = preferred_aggregation

    def export(self, metrics: Any, **kwargs: Any) -> Any:
        return self._inner.SUCCESS

    def shutdown(self, **kwargs: Any) -> None:
        return None

    def force_flush(self, **kwargs: Any) -> bool:
        return True


class NoOpSpanExporter:
    """Span exporter that drops all data."""

    def __init__(self, inner: Any | None = None) -> None:
        if inner is None:
            from opentelemetry.sdk.trace.export import SpanExportResult

            inner = SpanExportResult
        self._inner = inner

    def export(self, spans: Any) -> Any:
        return self._inner.SUCCESS

    def shutdown(self) -> None:
        return None

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        return True


def build_exporter(config: TelemetryConfig) -> ExporterBundle:
    """Create the requested span and metric exporters."""
    try:
        from opentelemetry.sdk.metrics.export import ConsoleMetricExporter, MetricExportResult
        from opentelemetry.sdk.trace.export import ConsoleSpanExporter, SpanExportResult
    except ImportError as exc:
        raise ImportError("OpenTelemetry SDK not installed. Run: pip install detent[telemetry]") from exc

    try:
        from opentelemetry.exporter.otlp.proto.grpc import (
            metric_exporter as otlp_metric_module,  # type: ignore[import-not-found]
        )
        from opentelemetry.exporter.otlp.proto.grpc import (
            trace_exporter as otlp_trace_module,  # type: ignore[import-not-found]
        )
    except ImportError:
        otlp_metric_exporter = None
        otlp_span_exporter = None
    else:
        otlp_metric_exporter = otlp_metric_module.OTLPMetricExporter
        otlp_span_exporter = otlp_trace_module.OTLPSpanExporter

    exporters: dict[str, tuple[Any, Any]] = {
        "console": (ConsoleSpanExporter(), ConsoleMetricExporter()),
        "none": (NoOpSpanExporter(SpanExportResult), NoOpMetricExporter(MetricExportResult)),
    }

    if otlp_span_exporter is not None and otlp_metric_exporter is not None:
        exporters["otlp"] = (
            otlp_span_exporter(endpoint=config.otlp_endpoint),
            otlp_metric_exporter(endpoint=config.otlp_endpoint),
        )
    elif config.exporter == "otlp":
        raise ImportError("OTLP exporters not installed. Run: pip install detent[telemetry]")

    try:
        span_exporter, metric_exporter = exporters[config.exporter]
    except KeyError as exc:
        raise ValueError(f"Unknown telemetry exporter: {config.exporter}") from exc

    return ExporterBundle(span_exporter=span_exporter, metric_exporter=metric_exporter)


__all__ = ["build_exporter", "NoOpMetricExporter", "NoOpSpanExporter"]
