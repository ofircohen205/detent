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

from typing import Any

from detent.adapters.http_proxy import HTTPProxyAdapter
from detent.schema import ActionType, AgentAction


class CodexAdapter(HTTPProxyAdapter):
    """Adapter for Codex tool call interception via HTTP proxy."""

    @property
    def agent_name(self) -> str:
        return "codex"

    @property
    def upstream_host(self) -> str:
        return "api.openai.com"

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction | None:
        tool_calls = raw_event.get("choices", [{}])[0].get("message", {}).get("tool_calls", [])
        for tool_call in tool_calls:
            action = self.normalize_tool_call(tool_call)
            if action and action.action_type == ActionType.FILE_WRITE:
                return action
        return None
