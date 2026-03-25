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

"""Provider-oriented HTTP response parsers for Point 1 observation."""

from __future__ import annotations

from typing import Any

from detent.adapters.http.base import OpenAICompatibleAdapter
from detent.adapters.http.claude_code import ClaudeCodeAdapter
from detent.config import UPSTREAM_HOST_ANTHROPIC, UPSTREAM_HOST_OPENAI


class AnthropicResponseAdapter(ClaudeCodeAdapter):
    """Provider parser for Anthropic-compatible response bodies."""

    def __init__(self, session_manager: Any, observed_agent: str) -> None:
        self._observed_agent = observed_agent
        super().__init__(session_manager=session_manager)

    @property
    def agent_name(self) -> str:
        return self._observed_agent

    @property
    def upstream_host(self) -> str:
        return UPSTREAM_HOST_ANTHROPIC


class OpenAIResponseAdapter(OpenAICompatibleAdapter):
    """Provider parser for OpenAI-compatible response bodies."""

    def __init__(self, session_manager: Any, observed_agent: str) -> None:
        self._observed_agent = observed_agent
        super().__init__(session_manager=session_manager)

    @property
    def agent_name(self) -> str:
        return self._observed_agent

    @property
    def upstream_host(self) -> str:
        return UPSTREAM_HOST_OPENAI
