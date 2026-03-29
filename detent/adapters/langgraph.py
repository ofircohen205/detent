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

"""LangGraph adapter for VerificationNode integration."""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import structlog

from detent.adapters.base import AgentAdapter
from detent.adapters.hook.base import _SUPPORTED_EXTENSIONS
from detent.schema import ActionType, AgentAction, RiskLevel

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class LangGraphAdapter(AgentAdapter):
    """Adapter for LangGraph VerificationNode integration.

    Insert VerificationNode into a LangGraph graph to gate tool calls:

        graph.add_node("verify", VerificationNode(adapter))
        graph.add_edge("agent", "verify")
        graph.add_edge("verify", "tools")
    """

    @property
    def agent_name(self) -> str:
        """Identifier for this adapter."""
        return "langgraph"

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction | None:
        """Normalize LangGraph tool call to AgentAction.

        Args:
            raw_event: Dict with tool_name, tool_input, tool_call_id

        Returns:
            Normalized AgentAction
        """
        start_time = time.perf_counter()
        self._log_intercept_start("tool_call")

        tool_name = raw_event.get("tool_name", "")
        tool_input = raw_event.get("tool_input", {})
        tool_call_id = raw_event.get("tool_call_id", "")

        if not tool_name:
            self._log_intercept_error("missing_field", "tool_name required")
            self._log_intercept_end(None)
            return None

        action_type = self._ACTION_TYPE_MAP.get(tool_name, ActionType.MCP_TOOL)

        if tool_name not in self._ACTION_TYPE_MAP:
            self._log_intercept_error("unknown_tool", f"unknown tool {tool_name!r}, treating as mcp_tool")

        # Only verify file-writes for supported languages
        if action_type == ActionType.FILE_WRITE:
            file_path = tool_input.get("file_path", "")
            if file_path and Path(file_path).suffix.lower() not in _SUPPORTED_EXTENSIONS:
                self._log_intercept_end(None)
                return None

        action = AgentAction(
            action_type=action_type,
            agent=self.agent_name,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_call_id=tool_call_id,
            session_id="",  # Set by VerificationNode
            checkpoint_ref="",  # Set by SessionManager
            risk_level=RiskLevel.MEDIUM,
        )

        self._log_intercept_end(action)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._log_performance("intercept", elapsed_ms)
        return action

    async def handle_verification_result(
        self,
        action: AgentAction,
        result: VerificationResult,
    ) -> dict[str, Any]:
        """Return allow/deny metadata for result."""
        start_time = time.perf_counter()
        self._log_result_handling_start(action)

        allow = result.passed or not any(f.severity == "error" for f in result.findings)
        decision = "allow" if allow else "deny"

        self._log_result_handling_end(action_allowed=allow)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._log_performance("handle_verification_result", elapsed_ms)
        return {"permissionDecision": decision}
