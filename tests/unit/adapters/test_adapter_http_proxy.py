"""Tests for HTTP proxy adapters."""

import json
from unittest.mock import MagicMock

import pytest

from detent.adapters.http.claude_code import ClaudeCodeAdapter
from detent.adapters.http.codex import CodexAdapter
from detent.adapters.http.providers import AnthropicResponseAdapter, OpenAIResponseAdapter
from detent.schema import ActionType


@pytest.mark.asyncio
async def test_codex_adapter_no_tool_calls_returns_none():
    """CodexAdapter should return None when no tool calls present."""
    adapter = CodexAdapter(session_manager=MagicMock())
    action = await adapter.intercept({"choices": [{"message": {}}]})
    assert action is None


@pytest.mark.asyncio
async def test_codex_adapter_intercept_response_responses_api_function_call():
    """CodexAdapter should parse Responses API function_call output items."""
    adapter = CodexAdapter(session_manager=MagicMock())
    response_body = json.dumps(
        {
            "output": [
                {
                    "type": "function_call",
                    "call_id": "call_123",
                    "name": "create_file",
                    "arguments": json.dumps({"file_path": "/src/main.py", "content": "x = 1"}),
                }
            ]
        }
    ).encode()

    actions = await adapter.intercept_response(response_body)

    assert len(actions) == 1
    assert actions[0].tool_call_id == "call_123"
    assert actions[0].tool_name == "create_file"
    assert actions[0].tool_input["file_path"] == "/src/main.py"


@pytest.mark.asyncio
async def test_codex_adapter_intercept_response_custom_tool_call():
    """CodexAdapter should parse Responses API custom tool calls using top-level input."""
    adapter = CodexAdapter(session_manager=MagicMock())
    response_body = json.dumps(
        {
            "output": [
                {
                    "type": "custom_tool_call",
                    "call_id": "call_456",
                    "name": "create_file",
                    "input": {"file_path": "/src/custom.py", "content": "y = 2"},
                }
            ]
        }
    ).encode()

    actions = await adapter.intercept_response(response_body)

    assert len(actions) == 1
    assert actions[0].tool_call_id == "call_456"
    assert actions[0].tool_input["file_path"] == "/src/custom.py"


@pytest.mark.asyncio
async def test_codex_adapter_intercept_response_mcp_call():
    """CodexAdapter should parse Responses API MCP calls using top-level input."""
    adapter = CodexAdapter(session_manager=MagicMock())
    response_body = json.dumps(
        {
            "output": [
                {
                    "type": "mcp_call",
                    "call_id": "call_654",
                    "name": "create_file",
                    "input": {"file_path": "/src/mcp.py", "content": "value = 4"},
                }
            ]
        }
    ).encode()

    actions = await adapter.intercept_response(response_body)

    assert len(actions) == 1
    assert actions[0].tool_call_id == "call_654"
    assert actions[0].tool_input["file_path"] == "/src/mcp.py"


@pytest.mark.asyncio
async def test_codex_adapter_intercept_response_ignores_non_action_output_items():
    """CodexAdapter should ignore text-like Responses API output items."""
    adapter = CodexAdapter(session_manager=MagicMock())
    response_body = json.dumps(
        {
            "output": [
                {"type": "reasoning", "summary": []},
                {"type": "message", "content": []},
                {
                    "type": "function_call",
                    "call_id": "call_789",
                    "name": "create_file",
                    "arguments": json.dumps({"file_path": "/src/keep.py", "content": "z = 3"}),
                },
            ]
        }
    ).encode()

    actions = await adapter.intercept_response(response_body)

    assert len(actions) == 1
    assert actions[0].tool_call_id == "call_789"


@pytest.mark.asyncio
async def test_codex_adapter_intercept_response_invalid_json_returns_empty_list():
    """CodexAdapter should return an empty list for invalid JSON bodies."""
    adapter = CodexAdapter(session_manager=MagicMock())

    actions = await adapter.intercept_response(b"{not json")

    assert actions == []


@pytest.mark.asyncio
async def test_codex_adapter_intercept_response_missing_output_returns_empty_list():
    """CodexAdapter should return an empty list when Responses API output is absent."""
    adapter = CodexAdapter(session_manager=MagicMock())

    actions = await adapter.intercept_response(json.dumps({"id": "resp_123"}).encode())

    assert actions == []


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


@pytest.mark.asyncio
async def test_provider_adapters_use_observed_agent_name():
    session_manager = MagicMock()

    anthropic = AnthropicResponseAdapter(session_manager=session_manager, observed_agent="cursor")
    openai = OpenAIResponseAdapter(session_manager=session_manager, observed_agent="codex")

    assert anthropic.agent_name == "cursor"
    assert openai.agent_name == "codex"
