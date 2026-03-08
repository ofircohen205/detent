import pytest
from detent.adapters.claude_code import ClaudeCodeAdapter
from detent.schema import AgentAction


@pytest.mark.asyncio
async def test_claude_code_adapter_normalizes_write_tool():
    """ClaudeCodeAdapter should normalize Claude Code Write tool input."""
    from unittest.mock import MagicMock

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
    from unittest.mock import MagicMock

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
