"""Adapter implementations for different AI agents."""

from detent.adapters.base import AgentAdapter
from detent.adapters.claude_code import ClaudeCodeAdapter
from detent.adapters.langgraph import LangGraphAdapter

ADAPTERS: dict[str, type[AgentAdapter]] = {
    "claude-code": ClaudeCodeAdapter,
    "langgraph": LangGraphAdapter,
}

__all__ = [
    "AgentAdapter",
    "ClaudeCodeAdapter",
    "LangGraphAdapter",
    "ADAPTERS",
]
