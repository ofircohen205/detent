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

"""Gemini adapter for HTTP hook interception."""

from __future__ import annotations

from typing import Any

import structlog

from detent.adapters.hook.base import HookAdapter
from detent.schema import ActionType, AgentAction, RiskLevel

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class GeminiAdapter(HookAdapter):
    """Adapter for Gemini CLI BeforeTool hook payloads."""

    @property
    def agent_name(self) -> str:
        return "gemini"

    @property
    def route(self) -> str:
        return "/hooks/gemini"

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction | None:
        if "tool_name" in raw_event:
            tool_name = raw_event.get("tool_name") or ""
            tool_input = raw_event.get("tool_input") or {}
        else:
            payload = raw_event.get("functionCall") or raw_event.get("function_call") or raw_event
            tool_name = payload.get("name") or ""
            tool_input = payload.get("args") or payload.get("arguments") or {}

        if not tool_name:
            raise ValueError("Missing tool_name in Gemini payload")

        tool_call_id = raw_event.get("tool_call_id") or raw_event.get("id") or ""
        session_id = raw_event.get("session_id", "")

        action_type = self._ACTION_TYPE_MAP.get(tool_name, ActionType.MCP_TOOL)
        if tool_name not in self._ACTION_TYPE_MAP:
            logger.warning("[gemini] unknown tool %s, treating as mcp_tool", tool_name)

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
