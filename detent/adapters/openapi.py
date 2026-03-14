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

"""Generic OpenAPI hook adapter."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from detent.adapters.hook import HookAdapter
from detent.schema import ActionType, AgentAction, RiskLevel

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from detent.proxy.session import SessionManager


class OpenAPIAdapter(HookAdapter):
    """Generic adapter for JSON tool call payloads over HTTP."""

    def __init__(self, session_manager: SessionManager, route: str = "/hooks/openapi") -> None:
        super().__init__(session_manager=session_manager)
        self._route = route

    @property
    def agent_name(self) -> str:
        return "openapi"

    @property
    def route(self) -> str:
        return self._route

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction | None:
        tool_name = raw_event.get("tool_name", "")
        tool_input = raw_event.get("tool_input")
        if not tool_name or tool_input is None:
            raise ValueError("Missing required fields: tool_name, tool_input")

        tool_call_id = raw_event.get("tool_call_id", "")
        session_id = raw_event.get("session_id", "")

        action_type = self._ACTION_TYPE_MAP.get(tool_name, ActionType.MCP_TOOL)
        if tool_name not in self._ACTION_TYPE_MAP:
            logger.warning("[openapi] unknown tool %s, treating as mcp_tool", tool_name)

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
