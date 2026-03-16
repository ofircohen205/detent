from unittest.mock import MagicMock

import pytest

from detent.adapters.http.claude_code import ClaudeCodeAdapter
from detent.pipeline.result import Finding, VerificationResult
from detent.schema import AgentAction


@pytest.mark.asyncio
async def test_claude_code_adapter_normalizes_write_tool():
    """ClaudeCodeAdapter should normalize Claude Code Write tool input."""
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())

    raw_event = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/src/main.py",
            "content": "print('hello')",
        },
        "tool_call_id": "toolu_01ABC123",
    }

    action = await adapter.intercept(raw_event)

    assert action.agent == "claude-code"
    assert action.tool_name == "Write"
    assert action.tool_input["file_path"] == "/src/main.py"
    assert action.tool_call_id == "toolu_01ABC123"
    assert action.action_type == "file_write"


@pytest.mark.asyncio
async def test_claude_code_adapter_normalizes_bash_tool():
    """ClaudeCodeAdapter should normalize Claude Code Bash tool input."""
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())

    raw_event = {
        "tool_name": "Bash",
        "tool_input": {
            "command": "ls -la /src",
        },
        "tool_call_id": "toolu_02DEF456",
    }

    action = await adapter.intercept(raw_event)

    assert action.tool_name == "Bash"
    assert action.action_type == "shell_exec"
    assert action.tool_input["command"] == "ls -la /src"
    assert action.agent == "claude-code"


@pytest.mark.asyncio
async def test_claude_code_adapter_unknown_tool_defaults_to_mcp_tool():
    """ClaudeCodeAdapter should default unknown tools to mcp_tool (safe default)."""
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())

    raw_event = {
        "tool_name": "UnknownTool",
        "tool_input": {
            "param": "value",
        },
        "tool_call_id": "toolu_03GHI789",
    }

    action = await adapter.intercept(raw_event)

    assert action.tool_name == "UnknownTool"
    assert action.action_type == "mcp_tool"
    assert action.agent == "claude-code"


@pytest.mark.asyncio
async def test_claude_code_adapter_allows_passing_verification():
    """ClaudeCodeAdapter should allow when verification passes."""
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())

    action = AgentAction(
        action_type="file_write",
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "x = 1"},
        tool_call_id="toolu_01",
        session_id="sess_1",
        checkpoint_ref="chk_1",
        risk_level="medium",
    )

    result = VerificationResult(
        stage="pipeline",
        passed=True,
        findings=[],
        duration_ms=100.0,
    )

    output = await adapter.handle_verification_result(action, result)
    assert output == {"hookSpecificOutput": {"permissionDecision": "allow"}}


@pytest.mark.asyncio
async def test_claude_code_adapter_blocks_on_syntax_error():
    """ClaudeCodeAdapter should deny when verification fails with errors."""
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())

    action = AgentAction(
        action_type="file_write",
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "x = "},
        tool_call_id="toolu_01",
        session_id="sess_1",
        checkpoint_ref="chk_1",
        risk_level="medium",
    )

    result = VerificationResult(
        stage="pipeline",
        passed=False,
        findings=[
            Finding(
                severity="error",
                file="/src/main.py",
                line=1,
                message="SyntaxError: invalid syntax",
                stage="syntax",
            )
        ],
        duration_ms=50.0,
    )

    output = await adapter.handle_verification_result(action, result)
    assert output == {"hookSpecificOutput": {"permissionDecision": "deny"}}
