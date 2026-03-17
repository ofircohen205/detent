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

"""Structlog configuration for Detent.

Call ``configure_logging()`` once at process startup (the CLI does this).
Library users get no-op stdlib logging by default and can call
``configure_logging()`` themselves if they want structured output.
"""

from __future__ import annotations

import logging
import sys

import structlog

_configured = False

# Processors shared between structlog-native calls and stdlib foreign calls.
_SHARED_PROCESSORS: list[structlog.types.Processor] = [
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.stdlib.PositionalArgumentsFormatter(),
    structlog.processors.StackInfoRenderer(),
]


def configure_logging(level: str = "INFO", *, json: bool = False) -> None:
    """Configure structlog + stdlib root logger.

    Args:
        level: Logging level string (``"DEBUG"``, ``"INFO"``, etc.).
        json:  Emit JSON lines instead of coloured console output.
               Defaults to ``False``. Set ``True`` in production / CI.
    """
    global _configured

    renderer: structlog.types.Processor = (
        structlog.processors.JSONRenderer() if json else structlog.dev.ConsoleRenderer(colors=sys.stderr.isatty())
    )

    structlog.configure(
        processors=[
            *_SHARED_PROCESSORS,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        wrapper_class=structlog.stdlib.BoundLogger,
        context_class=dict,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )

    formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
        foreign_pre_chain=_SHARED_PROCESSORS,
    )

    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())

    _configured = True
