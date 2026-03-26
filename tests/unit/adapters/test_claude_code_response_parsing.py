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


def _make_sse(events: list[dict]) -> bytes:
    """Build a minimal Anthropic SSE response body from a list of event dicts."""
    lines = []
    for event in events:
        lines.append(f"data: {json.dumps(event)}")
        lines.append("")
    lines.append("data: [DONE]")
    return "\n".join(lines).encode()


@pytest.mark.asyncio
async def test_intercept_response_sse_single_tool_use():
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())
    tool_input = {"file_path": "/tmp/main.py", "content": "print('hi')"}
    partial = json.dumps(tool_input)

    sse_body = _make_sse(
        [
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "tool_use", "id": "toolu_sse_1", "name": "Write"},
            },
            {"type": "content_block_delta", "index": 0, "delta": {"type": "input_json_delta", "partial_json": partial}},
            {"type": "content_block_stop", "index": 0},
        ]
    )

    actions = await adapter.intercept_response(sse_body)

    assert len(actions) == 1
    assert actions[0].tool_name == "Write"
    assert actions[0].tool_call_id == "toolu_sse_1"
    assert actions[0].tool_input["file_path"] == "/tmp/main.py"
    assert actions[0].action_type == ActionType.FILE_WRITE


@pytest.mark.asyncio
async def test_intercept_response_sse_multiple_tool_use_blocks():
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())

    sse_body = _make_sse(
        [
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "tool_use", "id": "toolu_a", "name": "Read"},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '{"file_path":"/a.py"}'},
            },
            {"type": "content_block_stop", "index": 0},
            {
                "type": "content_block_start",
                "index": 1,
                "content_block": {"type": "tool_use", "id": "toolu_b", "name": "Write"},
            },
            {
                "type": "content_block_delta",
                "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '{"file_path":"/b.py","content":"x=1"}'},
            },
            {"type": "content_block_stop", "index": 1},
        ]
    )

    actions = await adapter.intercept_response(sse_body)

    assert len(actions) == 2
    assert [a.tool_name for a in actions] == ["Read", "Write"]


@pytest.mark.asyncio
async def test_intercept_response_sse_split_partial_json():
    """Input JSON arrives in multiple delta chunks."""
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())

    sse_body = _make_sse(
        [
            {
                "type": "content_block_start",
                "index": 0,
                "content_block": {"type": "tool_use", "id": "toolu_split", "name": "Write"},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '{"file_path":'},
            },
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": '"/tmp/x.py","content":""}'},
            },
            {"type": "content_block_stop", "index": 0},
        ]
    )

    actions = await adapter.intercept_response(sse_body)

    assert len(actions) == 1
    assert actions[0].tool_input["file_path"] == "/tmp/x.py"


@pytest.mark.asyncio
async def test_intercept_response_sse_no_tool_use_returns_empty():
    adapter = ClaudeCodeAdapter(session_manager=MagicMock())

    sse_body = _make_sse(
        [
            {"type": "content_block_start", "index": 0, "content_block": {"type": "text"}},
            {"type": "content_block_delta", "index": 0, "delta": {"type": "text_delta", "text": "hello"}},
            {"type": "content_block_stop", "index": 0},
        ]
    )

    actions = await adapter.intercept_response(sse_body)

    assert actions == []
