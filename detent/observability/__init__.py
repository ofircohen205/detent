# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Detent Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""OpenTelemetry setup helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .exporter import build_exporter
from .logging import configure_logging
from .metrics import configure_metrics
from .tracer import configure_tracer

if TYPE_CHECKING:
    from detent.config import TelemetryConfig

_initialized = False


__all__ = ["configure_logging", "setup_telemetry"]


def setup_telemetry(config: TelemetryConfig) -> None:
    """Initialize OpenTelemetry providers and instruments."""
    global _initialized

    if _initialized or not config.enabled:
        return

    try:
        bundle = build_exporter(config)
    except ImportError as exc:
        raise ImportError("OpenTelemetry SDK not installed") from exc
    configure_tracer(config, bundle.span_exporter)
    configure_metrics(config, bundle.metric_exporter)
    _initialized = True
