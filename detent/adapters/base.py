"""Base class for agent adapters."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from detent.proxy.session import SessionManager
    from detent.schema import AgentAction


class AgentAdapter(ABC):
    """Base class for AI agent adapters.

    Each adapter translates agent-specific tool call events into the
    normalized AgentAction schema, then delegates to SessionManager
    for verification and checkpoint management.
    """

    agent_name: str

    def __init__(self, session_manager: SessionManager) -> None:
        """Initialize adapter.

        Args:
            session_manager: SessionManager for checkpoint + pipeline coordination
        """
        self.session_manager = session_manager

    @abstractmethod
    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction:
        """Normalize agent-specific event to AgentAction.

        Args:
            raw_event: Agent-specific event format (JSON from PreToolUse, LangGraph state, etc.)

        Returns:
            Normalized AgentAction

        Raises:
            NotImplementedError: Subclasses must implement
        """
