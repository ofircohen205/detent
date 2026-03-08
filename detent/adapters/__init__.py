"""Adapter implementations for different AI agents."""

from detent.adapters.base import AgentAdapter
from detent.adapters.claude_code import ClaudeCodeAdapter

ADAPTERS: dict[str, type[AgentAdapter]] = {
    "claude-code": ClaudeCodeAdapter,
}

__all__ = [
    "AgentAdapter",
    "ClaudeCodeAdapter",
    "ADAPTERS",
]
