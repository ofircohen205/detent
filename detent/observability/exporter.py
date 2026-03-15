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

from typing import TYPE_CHECKING

from detent.observability.schemas import ExporterBundle

if TYPE_CHECKING:
    from detent.config import TelemetryConfig


def build_exporter(config: TelemetryConfig) -> ExporterBundle:
    """Create the requested span and metric exporters."""
    try:
        from opentelemetry.sdk.metrics.export import (
            ConsoleMetricExporter,
            MetricExporter,
            NoOpMetricExporter,
            OTLPMetricExporter,
        )
        from opentelemetry.sdk.trace.export import (
            ConsoleSpanExporter,
            NoOpSpanExporter,
            OTLPSpanExporter,
            SpanExporter,
        )
    except ImportError as exc:
        raise ImportError("OpenTelemetry SDK not installed. Run: pip install detent[telemetry]") from exc

    exporters: dict[str, tuple[SpanExporter, MetricExporter]] = {
        "console": (ConsoleSpanExporter(), ConsoleMetricExporter()),
        "otlp": (
            OTLPSpanExporter(endpoint=config.otlp_endpoint),
            OTLPMetricExporter(endpoint=config.otlp_endpoint),
        ),
        "none": (NoOpSpanExporter(), NoOpMetricExporter()),
    }

    try:
        span_exporter, metric_exporter = exporters[config.exporter]
    except KeyError as exc:
        raise ValueError(f"Unknown telemetry exporter: {config.exporter}") from exc

    return ExporterBundle(span_exporter=span_exporter, metric_exporter=metric_exporter)
