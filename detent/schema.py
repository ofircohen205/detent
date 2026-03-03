"""Normalized action schema for all intercepted agent events.

Every agent adapter normalizes its raw events to AgentAction before
the verification pipeline runs. This keeps the pipeline agent-agnostic.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ActionType(StrEnum):
    """Types of actions an AI coding agent can perform."""

    FILE_WRITE = "file_write"
    SHELL_EXEC = "shell_exec"
    FILE_READ = "file_read"
    WEB_FETCH = "web_fetch"
    MCP_TOOL = "mcp_tool"


class RiskLevel(StrEnum):
    """Risk classification for an agent action."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AgentAction(BaseModel):
    """Normalized representation of an intercepted agent action.

    All agent adapters produce AgentAction instances. The verification
    pipeline always receives AgentAction — never raw agent-specific payloads.
    This is what makes new adapters cheap to add.
    """

    action_type: ActionType = Field(description="Type of action being performed")
    agent: str = Field(description='Agent identifier, e.g. "claude-code", "langgraph"')
    tool_name: str = Field(description='Tool name, e.g. "Write", "Bash", "Edit"')
    tool_input: dict[str, Any] = Field(description="Raw tool input (file_path, content, etc.)")
    tool_call_id: str = Field(description="Unique identifier for this tool call")
    session_id: str = Field(description="Session identifier")
    checkpoint_ref: str = Field(description='Checkpoint reference, e.g. "chk_before_write_004"')
    risk_level: RiskLevel = Field(default=RiskLevel.MEDIUM, description="Risk classification")

    @property
    def file_path(self) -> str | None:
        """Extract file_path from tool_input, if present."""
        return self.tool_input.get("file_path")

    @property
    def content(self) -> str | None:
        """Extract content from tool_input, if present."""
        return self.tool_input.get("content")

    @property
    def is_file_write(self) -> bool:
        """Check if this action is a file write."""
        return self.action_type == ActionType.FILE_WRITE
