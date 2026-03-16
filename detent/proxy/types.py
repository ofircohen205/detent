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

"""Type definitions and exceptions for proxy and IPC."""

from pydantic import BaseModel, Field

from detent.ipc.schemas import IPCMessage, IPCMessageType

__all__ = ["DetentSessionConflictError", "IPCMessage", "IPCMessageType", "SessionState"]


class DetentSessionConflictError(Exception):
    """Raised when attempting to start a session while one is already active."""

    pass


class SessionState(BaseModel):
    """Session metadata."""

    session_id: str
    started_at: str  # ISO 8601
    checkpoint_refs: list[str] = Field(default_factory=list)
    active_tool_call_id: str | None = None
