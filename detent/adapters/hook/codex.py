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

"""Codex hook adapter for pre-exec enforcement (Point 2)."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

from detent.adapters.hook.base import HookAdapter
from detent.schema import ActionType, AgentAction, RiskLevel

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult


class CodexHookAdapter(HookAdapter):
    """Adapter for OpenAI Codex CLI pre-execution hooks.

    Receives tool call events from the Codex hook mechanism (Point 2),
    runs full verification via intercept_tool_call (checkpoint + pipeline +
    rollback), and returns an approval decision.

    Supported payload formats (OpenAI-style):
    - Nested:   {"function": {"name": "...", "arguments": "..."}, "id": "..."}
    - Flat:     {"name": "...", "arguments": "{...}", "call_id": "..."}
    - With type: {"type": "function_call", "name": "...", "arguments": "...", "call_id": "..."}
    """

    @property
    def agent_name(self) -> str:
        return "codex"

    @property
    def route(self) -> str:
        return "/hooks/codex"

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction | None:
        """Normalize a Codex pre-exec hook event to AgentAction."""
        start_time = time.perf_counter()
        self._log_intercept_start("hook_event")

        # Nested OpenAI format: {"function": {"name": ..., "arguments": ...}, "id": ...}
        if "function" in raw_event and isinstance(raw_event["function"], dict):
            fn = raw_event["function"]
            tool_name = fn.get("name") or ""
            raw_input: Any = fn.get("arguments") or fn.get("params") or {}
            tool_call_id = raw_event.get("id") or raw_event.get("call_id") or ""
        else:
            # Flat format: {"name": ..., "arguments": ..., "call_id": ...}
            tool_name = raw_event.get("name") or raw_event.get("tool_name") or ""
            raw_input = raw_event.get("arguments") or raw_event.get("params") or raw_event.get("tool_input") or {}
            tool_call_id = raw_event.get("call_id") or raw_event.get("id") or ""

        if not tool_name:
            self._log_intercept_error("missing_field", "tool name required")
            self._log_intercept_end(None)
            return None

        # arguments is often a JSON-encoded string
        if isinstance(raw_input, str):
            try:
                tool_input = json.loads(raw_input)
                if not isinstance(tool_input, dict):
                    tool_input = {}
            except json.JSONDecodeError:
                self._log_intercept_error("json_decode", "failed to parse arguments string")
                tool_input = {}
        elif isinstance(raw_input, dict):
            tool_input = raw_input
        else:
            tool_input = {}

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
        """Return approval decision for Codex hook."""
        start_time = time.perf_counter()
        self._log_result_handling_start(action)

        allow = result.passed or not any(f.severity == "error" for f in result.findings)
        self._log_result_handling_end(action_allowed=allow)
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._log_performance("handle_verification_result", elapsed_ms)
        return {"approved": allow, "decision": "allow" if allow else "deny"}
