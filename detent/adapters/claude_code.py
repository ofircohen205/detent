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

"""Claude Code adapter for PreToolUse hook integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from detent.adapters.http_proxy import HTTPProxyAdapter
from detent.schema import ActionType, AgentAction, RiskLevel

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult

logger = logging.getLogger(__name__)


class ClaudeCodeAdapter(HTTPProxyAdapter):
    """Adapter for Claude Code's PreToolUse / PostToolUse hooks."""

    @property
    def agent_name(self) -> str:
        """Identifier for this adapter."""
        return "claude-code"

    @property
    def upstream_host(self) -> str:
        """Expected upstream host for Claude Code."""
        return "api.anthropic.com"

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction | None:
        """Normalize Claude Code tool call to AgentAction.

        Args:
            raw_event: Dict with tool_name, tool_input, tool_call_id

        Returns:
            Normalized AgentAction
        """
        if "hook_event_name" in raw_event:
            tool_name = raw_event.get("tool_name", "")
            tool_input = raw_event.get("tool_input", {})
            tool_call_id = raw_event.get("tool_call_id", "")
        else:
            tool_name = raw_event.get("tool_name") or raw_event.get("name") or ""
            tool_input = raw_event.get("tool_input") or raw_event.get("input") or {}
            tool_call_id = raw_event.get("tool_call_id") or raw_event.get("id") or ""

        if not tool_name:
            logger.debug("[claude-code] tool call missing name; skipping")
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

        return action

    async def handle_verification_result(
        self,
        action: AgentAction,
        result: VerificationResult,
    ) -> dict[str, Any]:
        """Return hook response with allow/deny permission decision."""
        allow = result.passed or not any(f.severity == "error" for f in result.findings)
        decision = "allow" if allow else "deny"
        return {"hookSpecificOutput": {"permissionDecision": decision}}
