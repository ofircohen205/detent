"""Tests for Claude Code hook adapter (Point 2 enforcement)."""

from unittest.mock import MagicMock

import pytest
from aiohttp import web

from detent.adapters.hook.claude_code import ClaudeCodeHookAdapter
from detent.pipeline.result import Finding, VerificationResult
from detent.schema import ActionType, AgentAction


@pytest.mark.asyncio
async def test_intercept_pretooluse_hook_event_write():
    """Parses a Claude Code PreToolUse hook event for the Write tool."""
    adapter = ClaudeCodeHookAdapter(session_manager=MagicMock())

    raw_event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Write",
        "tool_input": {"file_path": "/src/main.py", "content": "x = 1"},
        "tool_call_id": "toolu_hook_01",
        "session_id": "sess_abc",
    }

    action = await adapter.intercept(raw_event)

    assert action is not None
    assert action.agent == "claude-code"
    assert action.tool_name == "Write"
    assert action.action_type == ActionType.FILE_WRITE
    assert action.tool_call_id == "toolu_hook_01"
    assert action.session_id == "sess_abc"
    assert action.tool_input["file_path"] == "/src/main.py"


@pytest.mark.asyncio
async def test_intercept_pretooluse_hook_event_bash():
    """Parses a PreToolUse hook event for the Bash tool."""
    adapter = ClaudeCodeHookAdapter(session_manager=MagicMock())

    raw_event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "pytest tests/ -v"},
        "tool_call_id": "toolu_hook_02",
    }

    action = await adapter.intercept(raw_event)

    assert action is not None
    assert action.tool_name == "Bash"
    assert action.action_type == ActionType.SHELL_EXEC


@pytest.mark.asyncio
async def test_intercept_missing_tool_name_returns_none():
    """Returns None when tool_name is absent."""
    adapter = ClaudeCodeHookAdapter(session_manager=MagicMock())

    raw_event = {
        "hook_event_name": "PreToolUse",
        "tool_input": {"file_path": "/src/main.py"},
        "tool_call_id": "toolu_hook_03",
    }

    action = await adapter.intercept(raw_event)

    assert action is None


@pytest.mark.asyncio
async def test_intercept_unknown_tool_defaults_to_mcp_tool():
    """Unknown tools default to mcp_tool action type."""
    adapter = ClaudeCodeHookAdapter(session_manager=MagicMock())

    raw_event = {
        "hook_event_name": "PreToolUse",
        "tool_name": "CustomAgentTool",
        "tool_input": {},
        "tool_call_id": "toolu_hook_04",
    }

    action = await adapter.intercept(raw_event)

    assert action is not None
    assert action.action_type == ActionType.MCP_TOOL


@pytest.mark.asyncio
async def test_handle_verification_result_allow_on_pass():
    """Returns permissionDecision=allow when verification passes."""
    adapter = ClaudeCodeHookAdapter(session_manager=MagicMock())

    action = AgentAction(
        action_type="file_write",
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "x = 1"},
        tool_call_id="toolu_hook_05",
        session_id="sess_1",
        checkpoint_ref="chk_000",
        risk_level="medium",
    )
    result = VerificationResult(stage="pipeline", passed=True, findings=[], duration_ms=50.0)

    output = await adapter.handle_verification_result(action, result)

    assert output == {"hookSpecificOutput": {"permissionDecision": "allow"}}


@pytest.mark.asyncio
async def test_handle_verification_result_deny_on_error_finding():
    """Returns permissionDecision=deny when verification has an error finding."""
    adapter = ClaudeCodeHookAdapter(session_manager=MagicMock())

    action = AgentAction(
        action_type="file_write",
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "x ="},
        tool_call_id="toolu_hook_06",
        session_id="sess_1",
        checkpoint_ref="chk_001",
        risk_level="medium",
    )
    result = VerificationResult(
        stage="pipeline",
        passed=False,
        findings=[Finding(severity="error", file="/src/main.py", line=1, message="SyntaxError", stage="syntax")],
        duration_ms=30.0,
    )

    output = await adapter.handle_verification_result(action, result)

    assert output == {"hookSpecificOutput": {"permissionDecision": "deny"}}


@pytest.mark.asyncio
async def test_handle_verification_result_allow_on_warning_only():
    """Returns permissionDecision=allow when findings are warnings only."""
    adapter = ClaudeCodeHookAdapter(session_manager=MagicMock())

    action = AgentAction(
        action_type="file_write",
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "x = 1"},
        tool_call_id="toolu_hook_07",
        session_id="sess_1",
        checkpoint_ref="chk_002",
        risk_level="medium",
    )
    result = VerificationResult(
        stage="pipeline",
        passed=False,
        findings=[Finding(severity="warning", file="/src/main.py", line=1, message="line too long", stage="lint")],
        duration_ms=20.0,
    )

    output = await adapter.handle_verification_result(action, result)

    assert output == {"hookSpecificOutput": {"permissionDecision": "allow"}}


def test_hook_adapter_route():
    """Hook adapter registers at /hooks/claude-code."""
    adapter = ClaudeCodeHookAdapter(session_manager=MagicMock())
    assert adapter.route == "/hooks/claude-code"
    assert adapter.agent_name == "claude-code"


def test_hook_adapter_registers_on_app():
    """register() adds a POST route to the aiohttp app."""
    adapter = ClaudeCodeHookAdapter(session_manager=MagicMock())
    app = web.Application()
    adapter.register(app)

    routes = [r for r in app.router.routes() if r.method == "POST"]
    paths = [r.resource.canonical for r in routes]
    assert "/hooks/claude-code" in paths
