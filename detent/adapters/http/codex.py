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

from detent.adapters.http.base import OpenAICompatibleAdapter
from detent.config import UPSTREAM_HOST_OPENAI


class CodexAdapter(OpenAICompatibleAdapter):
    """Adapter for Codex tool call interception via HTTP proxy."""

    @property
    def agent_name(self) -> str:
        return "codex"

    @property
    def upstream_host(self) -> str:
        return UPSTREAM_HOST_OPENAI
