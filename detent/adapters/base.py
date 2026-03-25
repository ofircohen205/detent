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

    def _log_intercept_start(self, event_type: str) -> None:
        """Log adapter entry with event type.

        Args:
            event_type: Type of event being intercepted (e.g., 'tool_call')
        """
        logger.debug(
            "intercepting %s",
            event_type,
            agent=self.agent_name,
        )

    def _log_intercept_end(self, action: AgentAction | None) -> None:
        """Log action created or skipped.

        Args:
            action: The created AgentAction, or None if skipped
        """
        if action is None:
            logger.debug("action skipped", agent=self.agent_name)
        else:
            logger.debug(
                "action created",
                agent=self.agent_name,
                tool_name=action.tool_name,
                tool_call_id=action.tool_call_id,
                action_type=action.action_type.value,
            )

    def _log_intercept_error(self, error_type: str, reason: str) -> None:
        """Log parsing/validation failures.

        Args:
            error_type: Type of error (e.g., 'missing_field', 'json_decode')
            reason: Human-readable explanation
        """
        logger.warning(
            "intercept error",
            agent=self.agent_name,
            error_type=error_type,
            reason=reason,
        )

    def _log_result_handling_start(self, action: AgentAction) -> None:
        """Log verification result handling entry.

        Args:
            action: The action being handled
        """
        logger.debug(
            "handling verification result",
            agent=self.agent_name,
            tool_name=action.tool_name,
            tool_call_id=action.tool_call_id,
            action_type=action.action_type.value,
        )

    def _log_result_handling_end(self, allowed: bool) -> None:
        """Log verification decision.

        Args:
            allowed: Whether the action was allowed (True) or denied (False)
        """
        decision = "allowing" if allowed else "denying"
        logger.info(
            "%s execution",
            decision,
            agent=self.agent_name,
        )

    def _log_performance(self, operation: str, duration_ms: float) -> None:
        """Log execution time for an operation.

        Args:
            operation: Name of the operation (e.g., 'intercept')
            duration_ms: Duration in milliseconds
        """
        logger.debug(
            "%s completed in %.1fms",
            operation,
            duration_ms,
            agent=self.agent_name,
        )
