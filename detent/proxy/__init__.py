"""HTTP proxy for conversation-layer interception."""

from detent.proxy.http_proxy import DetentProxy
from detent.proxy.types import (
    DetentSessionConflictError,
    IPCMessage,
    IPCMessageType,
    SessionState,
)

__all__ = [
    "DetentProxy",
    "DetentSessionConflictError",
    "IPCMessage",
    "IPCMessageType",
    "SessionState",
]
