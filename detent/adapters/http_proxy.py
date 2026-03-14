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
import logging
from abc import abstractmethod
from typing import Any

from detent.adapters.base import AgentAdapter
from detent.schema import ActionType, AgentAction, RiskLevel

logger = logging.getLogger(__name__)


class HTTPProxyAdapter(AgentAdapter):
    """Adapter base for agents routed through DetentProxy."""

    @property
    @abstractmethod
    def upstream_host(self) -> str:
        """Expected upstream host, e.g. api.anthropic.com or api.openai.com."""

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
