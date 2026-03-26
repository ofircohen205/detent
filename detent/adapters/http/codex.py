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

"""Codex adapter for OpenAI-compatible HTTP proxy interception."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

from detent.adapters.http.base import OpenAICompatibleAdapter
from detent.config import UPSTREAM_HOST_OPENAI

if TYPE_CHECKING:
    from detent.schema import AgentAction


class CodexAdapter(OpenAICompatibleAdapter):
    """Adapter for Codex tool call interception via HTTP proxy."""

    @property
    def agent_name(self) -> str:
        return "codex"

    @property
    def upstream_host(self) -> str:
        return UPSTREAM_HOST_OPENAI

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction | None:
        """Normalize a Codex tool call to AgentAction with logging.

        Args:
            raw_event: OpenAI-compatible event dict (Chat Completions or Responses API)

        Returns:
            Normalized AgentAction for the first file-write tool call, or None
        """
        start_time = time.perf_counter()
        self._log_intercept_start("tool_call")

        action = await super().intercept(raw_event)

        if action is None:
            self._log_intercept_end(None)
        else:
            self._log_intercept_end(action)

        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._log_performance("intercept", elapsed_ms)

        return action

    async def intercept_response(self, resp_body: bytes) -> list[AgentAction]:
        """Parse a Codex response body for tool calls with logging.

        Args:
            resp_body: Raw HTTP response body bytes (JSON)

        Returns:
            List of AgentAction objects extracted from the response
        """
        start_time = time.perf_counter()
        stripped = resp_body.lstrip()
        content_type = "text/event-stream" if stripped.startswith(b"data:") else "application/json"
        self._log_response_parse_start(content_type)

        actions = await super().intercept_response(resp_body)

        self._log_response_parse_end(len(actions))
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        self._log_performance("intercept_response", elapsed_ms)

        return actions
