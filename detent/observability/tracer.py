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

"""Tracer configuration helpers for Detent."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterator

    from detent.config import TelemetryConfig

logger = logging.getLogger(__name__)

_configured = False


class _NoOpSpan:
    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        return None

    def set_attribute(self, name: str, value: Any) -> None:
        return None


class _NoOpTracer:
    @contextmanager
    def start_as_current_span(self, name: str, **kwargs: Any) -> Iterator[_NoOpSpan]:
        yield _NoOpSpan()


_noop_tracer = _NoOpTracer()


def configure_tracer(config: TelemetryConfig, exporter: Any) -> None:
    """Configure the global tracer provider."""
    global _configured

    if _configured:
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        raise ImportError("OpenTelemetry SDK not installed. Run: pip install detent[telemetry]") from exc

    resource = Resource.create({"service.name": config.service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(exporter))
    trace.set_tracer_provider(provider)
    _configured = True


def get_tracer(name: str | None = None) -> Any:
    """Return the active tracer (NoOp if not configured)."""
    if not _configured:
        return _noop_tracer
    from opentelemetry import trace

    return trace.get_tracer(name or __name__)
