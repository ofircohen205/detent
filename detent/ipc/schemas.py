from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class IPCMessageType(StrEnum):
    """IPC control channel message types."""

    SESSION_START = "session_start"
    TOOL_INTERCEPTED = "tool_intercepted"
    VERIFICATION_RESULT = "verification_result"
    ROLLBACK_INSTRUCTION = "rollback_instruction"
    SESSION_ERROR = "session_error"
    SESSION_END = "session_end"


class IPCMessage(BaseModel):
    """Normalized IPC message format (NDJSON)."""

    type: IPCMessageType = Field(description="Message type")
    data: dict[str, Any] = Field(description="Message payload")
    timestamp: str = Field(description="ISO 8601 timestamp")
