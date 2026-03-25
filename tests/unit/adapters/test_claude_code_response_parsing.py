"""Tests for Claude Code Anthropic response parsing."""

import json
from unittest.mock import MagicMock

import pytest

from detent.adapters.http.claude_code import ClaudeCodeAdapter
from detent.schema import ActionType


@pytest.mark.asyncio
async def test_intercept_response_single_tool_use():
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())
    response_body = json.dumps(
        {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_123",
                    "name": "Write",
                    "input": {"file_path": "/tmp/main.py", "content": "print('hi')"},
                }
            ]
        }
    ).encode()

    actions = await adapter.intercept_response(response_body)

    assert len(actions) == 1
    assert actions[0].action_type == ActionType.FILE_WRITE
    assert actions[0].tool_name == "Write"
    assert actions[0].tool_input["file_path"] == "/tmp/main.py"


@pytest.mark.asyncio
async def test_intercept_response_multiple_tool_use_blocks():
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())
    response_body = json.dumps(
        {
            "content": [
                {
                    "type": "tool_use",
                    "id": "toolu_1",
                    "name": "Read",
                    "input": {"file_path": "/tmp/a.py"},
                },
                {
                    "type": "tool_use",
                    "id": "toolu_2",
                    "name": "Write",
                    "input": {"file_path": "/tmp/b.py", "content": "x = 1"},
                },
            ]
        }
    ).encode()

    actions = await adapter.intercept_response(response_body)

    assert len(actions) == 2
    assert [action.tool_name for action in actions] == ["Read", "Write"]


@pytest.mark.asyncio
async def test_intercept_response_text_only_returns_empty_list():
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())

    actions = await adapter.intercept_response(json.dumps({"content": [{"type": "text", "text": "hello"}]}).encode())

    assert actions == []


@pytest.mark.asyncio
async def test_intercept_response_invalid_json_returns_empty_list():
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())

    actions = await adapter.intercept_response(b"{not json")

    assert actions == []


@pytest.mark.asyncio
async def test_intercept_response_missing_content_returns_empty_list():
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())

    actions = await adapter.intercept_response(json.dumps({"id": "msg_123"}).encode())

    assert actions == []


@pytest.mark.asyncio
async def test_intercept_response_mixed_content_filters_tool_use_items():
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())
    response_body = json.dumps(
        {
            "content": [
                {"type": "text", "text": "planning"},
                {
                    "type": "tool_use",
                    "id": "toolu_3",
                    "name": "Write",
                    "input": {"file_path": "/tmp/c.py", "content": "y = 2"},
                },
                {"type": "thinking", "thinking": "internal"},
            ]
        }
    ).encode()

    actions = await adapter.intercept_response(response_body)

    assert len(actions) == 1
    assert actions[0].tool_call_id == "toolu_3"
