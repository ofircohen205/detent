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

"""Adapter implementations for different AI agents."""

from detent.adapters.base import AgentAdapter
from detent.adapters.claude_code import ClaudeCodeAdapter
from detent.adapters.codex import CodexAdapter
from detent.adapters.cursor import CursorAdapter
from detent.adapters.gemini import GeminiAdapter
from detent.adapters.hook import HookAdapter
from detent.adapters.http_proxy import HTTPProxyAdapter
from detent.adapters.langgraph import LangGraphAdapter
from detent.adapters.litellm import LiteLLMAdapter
from detent.adapters.openapi import OpenAPIAdapter

ADAPTERS: dict[str, type[AgentAdapter]] = {
    "claude-code": ClaudeCodeAdapter,
    "cursor": CursorAdapter,
    "codex": CodexAdapter,
    "langgraph": LangGraphAdapter,
    "litellm": LiteLLMAdapter,
    "gemini": GeminiAdapter,
    "openapi": OpenAPIAdapter,
}

__all__ = [
    "AgentAdapter",
    "ClaudeCodeAdapter",
    "CursorAdapter",
    "CodexAdapter",
    "LangGraphAdapter",
    "LiteLLMAdapter",
    "GeminiAdapter",
    "OpenAPIAdapter",
    "HTTPProxyAdapter",
    "HookAdapter",
    "ADAPTERS",
]
