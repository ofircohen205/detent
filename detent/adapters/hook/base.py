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

"""Base adapter for HTTP hook interception (Point 2)."""

from __future__ import annotations

from abc import abstractmethod
from pathlib import Path

import structlog
from aiohttp import web

from detent.adapters.base import AgentAdapter
from detent.config.languages import is_verifiable_file

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class HookAdapter(AgentAdapter):
    """Adapter base for agents that POST tool calls via HTTP hooks."""

    _active: bool = False

    @property
    @abstractmethod
    def route(self) -> str:
        """Hook URL path, e.g. /hooks/gemini."""

    def register(self, app: web.Application) -> None:
        """Register the hook endpoint on the aiohttp app."""
        app.router.add_post(self.route, self._hook_handler)
        self._do_register()
        self._active = True

    def unregister(self, app: web.Application) -> None:
        """Unregister hook endpoint (best-effort)."""
        logger.warning("[hook] route removal not supported by aiohttp; adapter deactivated logically")
        self._do_unregister()
        self._active = False

    def _do_register(self) -> None:
        """Optional extra registration steps for subclasses."""

    def _do_unregister(self) -> None:
        """Optional extra teardown steps for subclasses."""

    async def _hook_handler(self, request: web.Request) -> web.Response:
        """Handle incoming hook POST requests."""
        try:
            raw_event = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON payload"}, status=400)

        try:
            action = await self.intercept(raw_event)
        except (KeyError, ValueError) as e:
            return web.json_response({"error": str(e)}, status=400)

        if action is None:
            logger.debug("[%s] hook event skipped (no actionable tool)", self.agent_name)
            return web.json_response({"status": "skipped"})

        file_path = action.file_path or ""
        if file_path and not is_verifiable_file(file_path):
            logger.debug(
                "[%s] hook event skipped (unsupported file: %s)",
                self.agent_name,
                Path(file_path).suffix or "(no extension)",
            )
            return web.json_response({"status": "skipped"})

        try:
            result = await self.session_manager.intercept_tool_call(action)
            output = await self.handle_verification_result(action, result)
            return web.json_response(output or {})
        except Exception as e:
            logger.error("[%s] intercept_tool_call raised unexpectedly: %s", self.agent_name, e)
            return web.json_response({"status": "error", "detail": "Detent internal error"})
