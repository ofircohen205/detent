"""Tests for HTTP proxy adapters."""

import json
from unittest.mock import MagicMock

import pytest

from detent.adapters.http.claude_code import ClaudeCodeAdapter
from detent.adapters.http.codex import CodexAdapter
from detent.adapters.http.cursor import CursorAdapter
from detent.schema import ActionType


@pytest.mark.asyncio
async def test_cursor_adapter_intercept_openai_tool_call():
    """CursorAdapter should normalize OpenAI tool calls."""
    adapter = CursorAdapter(session_manager=MagicMock())
    raw_event = {
        "choices": [
            {
                "message": {
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "function": {
                                "name": "create_file",
                                "arguments": json.dumps({"file_path": "/src/main.py", "content": "x = 1"}),
                            },
                        }
                    ]
                }
            }
        ]
    }

    action = await adapter.intercept(raw_event)
    assert action is not None
    assert action.action_type == ActionType.FILE_WRITE
    assert action.tool_name == "create_file"
    assert action.tool_input["file_path"] == "/src/main.py"


@pytest.mark.asyncio
async def test_codex_adapter_no_tool_calls_returns_none():
    """CodexAdapter should return None when no tool calls present."""
    adapter = CodexAdapter(session_manager=MagicMock())
    action = await adapter.intercept({"choices": [{"message": {}}]})
    assert action is None


@pytest.mark.asyncio
async def test_claude_code_adapter_hook_payload():
    """ClaudeCodeAdapter should handle hook payloads."""
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())
    raw_event = {
        "hook_event_name": "pre_tool_use",
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/file.py", "content": "print('hi')"},
        "tool_call_id": "toolu_123",
    }
    action = await adapter.intercept(raw_event)
    assert action is not None
    assert action.action_type == ActionType.FILE_WRITE
    assert action.tool_input["file_path"] == "/tmp/file.py"


@pytest.mark.asyncio
async def test_claude_code_handle_verification_result():
    """ClaudeCodeAdapter should allow or deny based on findings."""
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())
    action = MagicMock()

    passed_result = MagicMock(passed=True, findings=[])
    output = await adapter.handle_verification_result(action, passed_result)
    assert output["hookSpecificOutput"]["permissionDecision"] == "allow"

    failed_result = MagicMock(
        passed=False,
        findings=[MagicMock(severity="error")],
    )
    output = await adapter.handle_verification_result(action, failed_result)
    assert output["hookSpecificOutput"]["permissionDecision"] == "deny"
