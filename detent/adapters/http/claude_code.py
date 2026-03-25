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

"""Claude Code adapter for hook and Anthropic response integration."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

import structlog

from detent.adapters.http.base import HTTPProxyAdapter
from detent.config import UPSTREAM_HOST_ANTHROPIC
from detent.schema import ActionType, AgentAction, RiskLevel

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class ClaudeCodeAdapter(HTTPProxyAdapter):
    """Adapter for Claude Code's PreToolUse / PostToolUse hooks."""

    @property
    def agent_name(self) -> str:
        """Identifier for this adapter."""
        return "claude-code"

    @property
    def upstream_host(self) -> str:
        """Expected upstream host for Claude Code."""
        return UPSTREAM_HOST_ANTHROPIC

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction | None:
        """Normalize Claude Code tool call to AgentAction.

        Args:
            raw_event: Dict with tool_name, tool_input, tool_call_id

        Returns:
            Normalized AgentAction
        """
        start_time = time.perf_counter()

        self._log_intercept_start("tool_call")

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

        action_type = self._ACTION_TYPE_MAP.get(tool_name, ActionType.MCP_TOOL)
        if tool_name not in self._ACTION_TYPE_MAP:
            logger.warning("[claude-code] unknown tool %s, treating as mcp_tool", tool_name)
        else:
            logger.debug("[claude-code] intercepted %s tool call %s", tool_name, tool_call_id)

        action = AgentAction(
            action_type=action_type,
            agent=self.agent_name,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_call_id=tool_call_id,
            session_id="",  # Will be set by hook
            checkpoint_ref="",  # Will be set by SessionManager
            risk_level=RiskLevel.MEDIUM,
        )

        self._log_intercept_end(action)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._log_performance("intercept", elapsed_ms)

        return action

    async def intercept_response(self, resp_body: bytes) -> list[AgentAction]:
        """Parse an Anthropic API response body for tool_use content blocks.

        Handles both non-streaming JSON responses and SSE streaming responses.
        """
        start_time = time.perf_counter()

        stripped = resp_body.lstrip()
        content_type = "text/event-stream" if stripped.startswith(b"data:") else "application/json"
        self._log_response_parse_start(content_type)

        if stripped.startswith(b"data:"):
            actions = self._parse_sse_response(resp_body)
        else:
            try:
                data = json.loads(resp_body)
            except json.JSONDecodeError:
                logger.debug("[claude-code] response body is not JSON or SSE; skipping")
                self._log_response_parse_end(0)
                return []

            content = data.get("content", [])
            if not isinstance(content, list):
                self._log_response_parse_end(0)
                return []

            actions: list[AgentAction] = []
            for item in content:
                if not isinstance(item, dict) or item.get("type") != "tool_use":
                    continue
                action = self.normalize_tool_call(item)
                if action is not None:
                    actions.append(action)

        self._log_response_parse_end(len(actions))

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._log_performance("intercept_response", elapsed_ms)

        return actions

    def _parse_sse_response(self, resp_body: bytes) -> list[AgentAction]:
        """Reconstruct tool_use blocks from an Anthropic SSE streaming response.

        Anthropic streams tool calls across three event types:
          - content_block_start  (type=tool_use): opens a block, gives id + name
          - content_block_delta  (type=input_json_delta): appends partial_json
          - content_block_stop: closes the block; input JSON is now complete
        """
        # index -> {id, name, partial_json}
        in_progress: dict[int, dict[str, Any]] = {}
        actions: list[AgentAction] = []

        for line in resp_body.decode("utf-8", errors="replace").splitlines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if not payload or payload == "[DONE]":
                continue
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                self._log_intercept_error("json_decode", "malformed SSE event")
                continue

            event_type = event.get("type")

            if event_type == "content_block_start":
                block = event.get("content_block", {})
                if block.get("type") == "tool_use":
                    idx = event.get("index", 0)
                    in_progress[idx] = {
                        "id": block.get("id", ""),
                        "name": block.get("name", ""),
                        "partial_json": "",
                    }
                    logger.debug(
                        "[claude-code] SSE tool_use block started",
                        tool_name=block.get("name"),
                        block_id=block.get("id"),
                    )

            elif event_type == "content_block_delta":
                idx = event.get("index", 0)
                if idx in in_progress:
                    delta = event.get("delta", {})
                    if delta.get("type") == "input_json_delta":
                        in_progress[idx]["partial_json"] += delta.get("partial_json", "")

            elif event_type == "content_block_stop":
                idx = event.get("index", 0)
                if idx not in in_progress:
                    continue
                block_info = in_progress.pop(idx)
                try:
                    tool_input = json.loads(block_info["partial_json"]) if block_info["partial_json"] else {}
                except json.JSONDecodeError:
                    self._log_intercept_error(
                        "json_decode",
                        "invalid input_json in SSE tool_use block",
                    )
                    tool_input = {}
                item = {
                    "type": "tool_use",
                    "id": block_info["id"],
                    "name": block_info["name"],
                    "input": tool_input,
                }
                action = self.normalize_tool_call(item)
                if action is not None:
                    actions.append(action)
                    logger.debug(
                        "[claude-code] SSE tool_use block completed",
                        tool_name=block_info["name"],
                    )

        return actions

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
