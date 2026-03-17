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

"""LiteLLM adapter (observability-only)."""

from __future__ import annotations

import importlib
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import structlog
from aiohttp import web

from detent.adapters.hook.base import HookAdapter
from detent.ipc.schemas import IPCMessage, IPCMessageType
from detent.schema import ActionType, AgentAction, RiskLevel

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult


class LiteLLMAdapter(HookAdapter):
    """Observability-only adapter for LiteLLM callbacks."""

    @property
    def agent_name(self) -> str:
        return "litellm"

    @property
    def route(self) -> str:
        return "/hooks/litellm"

    def _do_register(self) -> None:
        try:
            litellm = importlib.import_module("litellm")
        except Exception as e:
            logger.warning("[litellm] unable to import litellm: %s", e)
            return

        if self not in litellm.callbacks:
            litellm.callbacks.append(self)

    def _do_unregister(self) -> None:
        try:
            litellm = importlib.import_module("litellm")
        except Exception:
            return

        if self in litellm.callbacks:
            litellm.callbacks.remove(self)

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction | None:
        tool_name = raw_event.get("tool_name", "")
        tool_input = raw_event.get("tool_input")
        if not tool_name or tool_input is None:
            raise ValueError("Missing required fields: tool_name, tool_input")

        tool_call_id = raw_event.get("tool_call_id", "")
        session_id = raw_event.get("session_id", "")

        action_type = self._ACTION_TYPE_MAP.get(tool_name, ActionType.MCP_TOOL)
        if tool_name not in self._ACTION_TYPE_MAP:
            logger.warning("[litellm] unknown tool %s, treating as mcp_tool", tool_name)

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

    async def _observe_action(self, action: AgentAction) -> VerificationResult | None:
        try:
            result = await self.session_manager.pipeline.run(action)
        except Exception as e:
            logger.error("[litellm] pipeline run failed: %s", e)
            await self.session_manager.ipc_channel.send_message(
                IPCMessage(
                    type=IPCMessageType.VERIFICATION_RESULT,
                    data={
                        "tool_call_id": action.tool_call_id,
                        "status": "error",
                        "error": str(e),
                    },
                    timestamp=datetime.now(UTC).isoformat(),
                )
            )
            return None

        await self.session_manager.ipc_channel.send_message(
            IPCMessage(
                type=IPCMessageType.VERIFICATION_RESULT,
                data={
                    "tool_call_id": action.tool_call_id,
                    "status": "observed",
                    "passed": result.passed,
                },
                timestamp=datetime.now(UTC).isoformat(),
            )
        )
        return result

    async def _hook_handler(self, request: web.Request) -> web.Response:
        try:
            raw_event = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON payload"}, status=400)

        try:
            action = await self.intercept(raw_event)
        except (KeyError, ValueError) as e:
            return web.json_response({"error": str(e)}, status=400)

        if action is None:
            logger.debug("[litellm] hook event skipped (no actionable tool)")
            return web.json_response({"status": "skipped"})

        await self._observe_action(action)
        return web.json_response({"status": "observed"})

    async def handle_event(self, raw_event: dict[str, Any]) -> VerificationResult | None:
        action = await self.intercept(raw_event)
        if action is None:
            return None
        return await self._observe_action(action)
