"""Claude Code adapter for PreToolUse hook integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from detent.adapters.base import AgentAdapter
from detent.schema import ActionType, AgentAction, RiskLevel

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult

logger = logging.getLogger(__name__)


class ClaudeCodeAdapter(AgentAdapter):
    """Adapter for Claude Code's PreToolUse / PostToolUse hooks."""

    @property
    def agent_name(self) -> str:
        """Identifier for this adapter."""
        return "claude-code"

    async def intercept(self, raw_event: dict[str, Any]) -> AgentAction:
        """Normalize Claude Code tool call to AgentAction.

        Args:
            raw_event: Dict with tool_name, tool_input, tool_call_id

        Returns:
            Normalized AgentAction
        """
        tool_name = raw_event.get("tool_name", "")
        tool_input = raw_event.get("tool_input", {})
        tool_call_id = raw_event.get("tool_call_id", "")

        # Map Claude Code tools to action types
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
                "[claude-code] unknown tool %s, treating as mcp_tool",
                tool_name,
            )
        else:
            logger.debug(
                "[claude-code] intercepted %s tool call %s",
                tool_name,
                tool_call_id,
            )

        action = AgentAction(
            action_type=action_type,
            agent=self.agent_name,
            tool_name=tool_name,
            tool_input=tool_input,
            tool_call_id=tool_call_id,
            session_id="",  # Will be set by hook
            checkpoint_ref="",  # Will be set by SessionManager
            risk_level=RiskLevel.MEDIUM,
        )

        return action

    async def handle_verification_result(
        self,
        action: AgentAction,
        result: VerificationResult,
    ) -> dict[str, Any] | None:
        """Process verification result and decide: allow / modify / block.

        Args:
            action: The verified action
            result: Verification pipeline result

        Returns:
            None to allow execution, dict of modified tool_input for fixes

        Raises:
            ValueError: If verification found errors (syntax, typecheck, tests)
        """
        if result.passed:
            logger.info(
                "[claude-code] verification passed for %s, allowing execution",
                action.tool_name,
            )
            return None

        # Check for errors vs warnings
        errors = [f for f in result.findings if f.severity == "error"]
        warnings = [f for f in result.findings if f.severity == "warning"]

        if errors:
            # Block on any error (syntax, typecheck, test failure)
            msg = f"Verification failed: {len(errors)} error(s) found"
            logger.error("[claude-code] blocking %s: %s", action.tool_name, msg)
            raise ValueError(msg)

        if warnings:
            # Lint/format issues only - could apply ruff fixes here
            logger.info(
                "[claude-code] %d warning(s) found for %s, would apply ruff fixes",
                len(warnings),
                action.tool_name,
            )
            return None

        return None
