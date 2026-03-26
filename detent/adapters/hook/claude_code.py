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

"""Claude Code hook adapter for PreToolUse / PostToolUse enforcement (Point 2)."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from detent.adapters.hook.base import HookAdapter
from detent.schema import ActionType, AgentAction, RiskLevel

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult


class ClaudeCodeHookAdapter(HookAdapter):
    """Adapter for Claude Code PreToolUse hooks.

    Receives tool call events from Claude Code's hook mechanism (Point 2),
    runs full verification via intercept_tool_call (checkpoint + pipeline +
    rollback), and returns a permissionDecision to allow or deny execution.
    """

    @property
    def agent_name(self) -> str:
        return "claude-code"

    @property
    def route(self) -> str:
        return "/hooks/claude-code"

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction | None:
        """Normalize a Claude Code PreToolUse hook event to AgentAction.

        Claude Code PreToolUse events include a ``hook_event_name`` key.
        The adapter also accepts raw tool call dicts (e.g. from tests).
        """
        start_time = time.perf_counter()
        self._log_intercept_start("hook_event")

        if "hook_event_name" in raw_event:
            tool_name = raw_event.get("tool_name", "")
            tool_input = raw_event.get("tool_input", {})
            tool_call_id = raw_event.get("tool_call_id", "")
        else:
            tool_name = raw_event.get("tool_name") or raw_event.get("name") or ""
            tool_input = raw_event.get("tool_input") or raw_event.get("input") or {}
            tool_call_id = raw_event.get("tool_call_id") or raw_event.get("id") or ""

        if not tool_name:
            self._log_intercept_error("missing_field", "tool_name required")
            self._log_intercept_end(None)
            return None

        session_id = raw_event.get("session_id", "")

        action_type = self._ACTION_TYPE_MAP.get(tool_name, ActionType.MCP_TOOL)
        if tool_name not in self._ACTION_TYPE_MAP:
            self._log_intercept_error("unknown_tool", f"unknown tool '{tool_name}', treating as mcp_tool")

        action = AgentAction(
            action_type=action_type,
            agent=self.agent_name,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_call_id=tool_call_id,
            session_id=session_id,
            checkpoint_ref="",
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
        """Return hook response with allow/deny permission decision."""
        start_time = time.perf_counter()
        self._log_result_handling_start(action)

        allow = result.passed or not any(f.severity == "error" for f in result.findings)
        decision = "allow" if allow else "deny"

        self._log_result_handling_end(action_allowed=allow)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._log_performance("handle_verification_result", elapsed_ms)
        return {"hookSpecificOutput": {"permissionDecision": decision}}
