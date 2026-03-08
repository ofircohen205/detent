"""IPC control channel for adapter communication."""

from detent.ipc.channel import IPCControlChannel
from detent.proxy.types import IPCMessage, IPCMessageType

__all__ = ["IPCControlChannel", "IPCMessage", "IPCMessageType"]
