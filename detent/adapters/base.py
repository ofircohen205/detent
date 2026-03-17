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

"""Base class for agent adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

import structlog

from detent.schema import ActionType

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult
    from detent.proxy.session import SessionManager
    from detent.schema import AgentAction

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class AgentAdapter(ABC):
    """Base class for AI agent adapters.

    Each adapter translates agent-specific tool call events into the
    normalized AgentAction schema, then delegates to SessionManager
    for verification and checkpoint management.
    """

    _ACTION_TYPE_MAP: dict[str, ActionType] = {
        "Write": ActionType.FILE_WRITE,
        "Edit": ActionType.FILE_WRITE,
        "Bash": ActionType.SHELL_EXEC,
        "Read": ActionType.FILE_READ,
        "WebFetch": ActionType.WEB_FETCH,
        "create_file": ActionType.FILE_WRITE,
        "run_command": ActionType.SHELL_EXEC,
        "read_file": ActionType.FILE_READ,
    }

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Identifier for this adapter, e.g. 'claude-code', 'langgraph'."""

    def __init__(self, session_manager: SessionManager) -> None:
        """Initialize adapter.

        Args:
            session_manager: SessionManager for checkpoint + pipeline coordination
        """
        self.session_manager = session_manager
        logger.debug("Initialized %s adapter", self.agent_name)

    @abstractmethod
    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction | None:
        """Normalize agent-specific event to AgentAction.

        Args:
            raw_event: Agent-specific event format (JSON from PreToolUse, LangGraph state, etc.)

        Returns:
            Normalized AgentAction, or None to skip verification
        """

    async def handle_verification_result(
        self,
        action: AgentAction,
        result: VerificationResult,
    ) -> dict[str, Any]:
        """Return hook-specific output for verification results.

        Default behavior is a no-op allow decision.
        """
        return {}
