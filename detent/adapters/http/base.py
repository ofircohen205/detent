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

"""Base adapter for HTTP proxy interception (Point 1)."""

from __future__ import annotations

import json
from abc import abstractmethod
from typing import Any

import structlog

from detent.adapters.base import AgentAdapter
from detent.schema import ActionType, AgentAction, RiskLevel

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class HTTPProxyAdapter(AgentAdapter):
    """Adapter base for agents routed through DetentProxy."""

    @property
    @abstractmethod
    def upstream_host(self) -> str:
        """Expected upstream host, e.g. api.anthropic.com or api.openai.com."""

    @abstractmethod
    async def intercept_response(self, resp_body: bytes) -> list[AgentAction]:
        """Parse an LLM API response and return actionable tool calls."""

    def _log_http_intercept(self, method: str, path: str) -> None:
        """Log HTTP request interception at DEBUG level.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: URL path being intercepted
        """
        logger.debug(
            "intercepting HTTP request",
            agent=self.agent_name,
            method=method,
            path=path,
            upstream_host=self.upstream_host,
        )

    def _log_response_parse_start(self, content_type: str) -> None:
        """Log response parsing entry at DEBUG level.

        Args:
            content_type: Content-Type header value
        """
        parse_type = "SSE" if "event-stream" in content_type else "JSON"
        logger.debug(
            "parsing response as %s",
            parse_type,
            agent=self.agent_name,
            content_type=content_type,
        )

    def _log_response_parse_end(self, action_count: int) -> None:
        """Log tool calls extracted from response at DEBUG level.

        Args:
            action_count: Number of tool_use blocks parsed
        """
        logger.debug(
            "parsed %d tool_use blocks from response",
            action_count,
            agent=self.agent_name,
        )

    def normalize_tool_call(self, raw_tool: dict[str, Any]) -> AgentAction | None:
        """Normalize a raw tool call dict to AgentAction.

        Returns None if tool name is missing.
        """
        tool_name = ""
        tool_input: dict[str, Any] = {}

        if "function" in raw_tool:
            tool_name = raw_tool.get("function", {}).get("name", "") or ""
            arguments = raw_tool.get("function", {}).get("arguments", {})
            if isinstance(arguments, str):
                try:
                    tool_input = json.loads(arguments)
                except json.JSONDecodeError:
                    logger.warning(
                        "[%s] failed to parse OpenAI tool arguments for %s",
                        self.agent_name,
                        tool_name,
                    )
                    tool_input = {"raw_arguments": arguments}
            elif isinstance(arguments, dict):
                tool_input = arguments
        else:
            tool_name = raw_tool.get("name") or raw_tool.get("tool_name") or ""
            tool_input = raw_tool.get("input") or raw_tool.get("tool_input") or {}

        if not tool_name:
            logger.debug("[%s] tool call missing name; skipping", self.agent_name)
            return None

        action_type = self._ACTION_TYPE_MAP.get(tool_name, ActionType.MCP_TOOL)
        if tool_name not in self._ACTION_TYPE_MAP:
            logger.warning(
                "[%s] unknown tool %s, treating as mcp_tool",
                self.agent_name,
                tool_name,
            )

        tool_call_id = raw_tool.get("id") or raw_tool.get("tool_call_id") or ""
        session_id = raw_tool.get("session_id", "")

        return AgentAction(
            action_type=action_type,
            agent=self.agent_name,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_call_id=tool_call_id,
            session_id=session_id,
            checkpoint_ref="",
            risk_level=RiskLevel.MEDIUM,
        )


class OpenAICompatibleAdapter(HTTPProxyAdapter):
    """Shared intercept logic for OpenAI-compatible agents (Codex, Cursor, etc.)."""

    _RESPONSES_API_TOOL_TYPES = frozenset({"function_call", "custom_tool_call", "mcp_call"})

    def _coerce_tool_input(self, raw_input: Any, tool_name: str) -> dict[str, Any]:
        if isinstance(raw_input, dict):
            return raw_input
        if isinstance(raw_input, str):
            try:
                parsed = json.loads(raw_input)
            except json.JSONDecodeError:
                logger.warning("[%s] failed to parse tool payload for %s", self.agent_name, tool_name)
                return {"raw_input": raw_input}
            if isinstance(parsed, dict):
                return parsed
            return {"value": parsed}
        return {}

    def normalize_tool_call(self, raw_tool: dict[str, Any]) -> AgentAction | None:
        if "function" in raw_tool:
            tool_name = raw_tool.get("function", {}).get("name", "") or ""
            raw_input = raw_tool.get("function", {}).get("arguments", {})
        else:
            tool_name = raw_tool.get("name") or raw_tool.get("tool_name") or ""
            raw_input = raw_tool.get("arguments")
            if raw_input is None:
                raw_input = raw_tool.get("input")
            if raw_input is None:
                raw_input = raw_tool.get("tool_input")

        if not tool_name:
            logger.debug("[%s] tool call missing name; skipping", self.agent_name)
            return None

        tool_input = self._coerce_tool_input(raw_input, tool_name)
        action_type = self._ACTION_TYPE_MAP.get(tool_name, ActionType.MCP_TOOL)
        if tool_name not in self._ACTION_TYPE_MAP:
            logger.warning("[%s] unknown tool %s, treating as mcp_tool", self.agent_name, tool_name)

        tool_call_id = raw_tool.get("call_id") or raw_tool.get("id") or raw_tool.get("tool_call_id") or ""
        session_id = raw_tool.get("session_id", "")

        return AgentAction(
            action_type=action_type,
            agent=self.agent_name,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_call_id=tool_call_id,
            session_id=session_id,
            checkpoint_ref="",
            risk_level=RiskLevel.MEDIUM,
        )

    def _extract_chat_completions_tool_calls(self, raw_event: dict[str, Any]) -> list[AgentAction]:
        tool_calls = raw_event.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
        actions: list[AgentAction] = []
        for tool_call in tool_calls:
            action = self.normalize_tool_call(tool_call)
            if action is not None:
                actions.append(action)
        return actions

    def _extract_responses_api_tool_calls(self, raw_event: dict[str, Any]) -> list[AgentAction]:
        output = raw_event.get("output", [])
        if not isinstance(output, list):
            return []

        actions: list[AgentAction] = []
        for item in output:
            if not isinstance(item, dict):
                continue
            if item.get("type") not in self._RESPONSES_API_TOOL_TYPES:
                continue
            action = self.normalize_tool_call(item)
            if action is not None:
                actions.append(action)
        return actions

    def _extract_tool_calls(self, raw_event: dict[str, Any]) -> list[AgentAction]:
        actions = self._extract_chat_completions_tool_calls(raw_event)
        actions.extend(self._extract_responses_api_tool_calls(raw_event))
        return actions

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction | None:
        for action in self._extract_tool_calls(raw_event):
            if action and action.action_type == ActionType.FILE_WRITE:
                return action
        return None

    async def intercept_response(self, resp_body: bytes) -> list[AgentAction]:
        try:
            raw_event = json.loads(resp_body)
        except json.JSONDecodeError:
            logger.warning("[%s] failed to parse response body as JSON", self.agent_name)
            return []
        return self._extract_tool_calls(raw_event)
