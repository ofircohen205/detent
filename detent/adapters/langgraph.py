"""LangGraph adapter for VerificationNode integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from detent.adapters.base import AgentAdapter
from detent.schema import ActionType, AgentAction, RiskLevel

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult

logger = logging.getLogger(__name__)


class LangGraphAdapter(AgentAdapter):
    """Adapter for LangGraph VerificationNode integration.

    Insert VerificationNode into a LangGraph graph to gate tool calls:

        graph.add_node("verify", VerificationNode(adapter))
        graph.add_edge("agent", "verify")
        graph.add_edge("verify", "tools")
    """

    @property
    def agent_name(self) -> str:
        """Identifier for this adapter."""
        return "langgraph"

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction:
        """Normalize LangGraph tool call to AgentAction.

        Args:
            raw_event: Dict with tool_name, tool_input, tool_call_id

        Returns:
            Normalized AgentAction
        """
        tool_name = raw_event.get("tool_name", "")
        tool_input = raw_event.get("tool_input", {})
        tool_call_id = raw_event.get("tool_call_id", "")

        # Map tool names to action types (same as Claude Code)
        action_type_map: dict[str, ActionType] = {
            "Write": ActionType.FILE_WRITE,
            "Edit": ActionType.FILE_WRITE,
            "Bash": ActionType.SHELL_EXEC,
            "Read": ActionType.FILE_READ,
            "WebFetch": ActionType.WEB_FETCH,
        }
        action_type = action_type_map.get(tool_name, ActionType.MCP_TOOL)

        if tool_name not in action_type_map:
            logger.warning(
                "[langgraph] unknown tool %s, treating as mcp_tool",
                tool_name,
            )
        else:
            logger.debug(
                "[langgraph] intercepted %s tool call %s",
                tool_name,
                tool_call_id,
            )

        action = AgentAction(
            action_type=action_type,
            agent=self.agent_name,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_call_id=tool_call_id,
            session_id="",  # Set by VerificationNode
            checkpoint_ref="",  # Set by SessionManager
            risk_level=RiskLevel.MEDIUM,
        )

        return action

    async def handle_verification_result(
        self,
        action: AgentAction,
        result: VerificationResult,
    ) -> dict[str, Any] | None:
        """Process verification result.

        Args:
            action: The verified action
            result: Verification pipeline result

        Returns:
            None to allow, dict of modified tool_input for fixes

        Raises:
            ValueError: If verification found errors
        """
        if result.passed:
            logger.info(
                "[langgraph] verification passed for %s, allowing execution",
                action.tool_name,
            )
            return None

        # Check for errors vs warnings
        errors = [f for f in result.findings if f.severity == "error"]
        warnings = [f for f in result.findings if f.severity == "warning"]

        if errors:
            msg = f"Verification failed: {len(errors)} error(s) found"
            logger.error("[langgraph] blocking %s: %s", action.tool_name, msg)
            raise ValueError(msg)

        if warnings:
            logger.info(
                "[langgraph] %d warning(s) found for %s, would apply ruff fixes",
                len(warnings),
                action.tool_name,
            )
            return None

        return None
