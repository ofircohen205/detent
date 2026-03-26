# SPDX-License-Identifier: Apache-2.0

import json
from unittest.mock import MagicMock

import pytest
import structlog.testing

from detent.adapters.http.claude_code import ClaudeCodeAdapter
from detent.proxy.session import SessionManager


@pytest.fixture
def mock_session_manager():
    return MagicMock(spec=SessionManager)


@pytest.fixture
def claude_code_adapter(mock_session_manager):
    return ClaudeCodeAdapter(mock_session_manager)


@pytest.mark.asyncio
async def test_intercept_logs_tool_call_flow(claude_code_adapter):
    """Verify complete log sequence for a successful tool call intercept."""
    raw_event = {
        "tool_name": "Write",
        "tool_input": {"file_path": "src/main.py", "content": "print('hello')"},
        "tool_call_id": "call_001",
    }

    with structlog.testing.capture_logs() as logs:
        action = await claude_code_adapter.intercept(raw_event)

    assert action is not None
    assert action.tool_name == "Write"

    events = [entry["event"] for entry in logs]
    # intercept start log
    assert any("intercepting" in e for e in events)
    # action created log
    assert any("action created" in e for e in events)
    # performance log
    assert any("intercept" in e and "ms" in e for e in events)


@pytest.mark.asyncio
async def test_intercept_logs_missing_tool_name(claude_code_adapter):
    """Verify logging when tool_name is missing from event."""
    raw_event = {
        "tool_input": {"file_path": "src/main.py"},
        "tool_call_id": "call_002",
    }

    with structlog.testing.capture_logs() as logs:
        action = await claude_code_adapter.intercept(raw_event)

    assert action is None

    warning_logs = [entry for entry in logs if entry.get("log_level") == "warning"]
    assert len(warning_logs) > 0
    assert any(
        entry.get("error_type") == "missing_field" or "tool_name" in entry.get("event", "") for entry in warning_logs
    )


@pytest.mark.asyncio
async def test_intercept_response_json_logs_parse_flow(claude_code_adapter):
    """Verify logging during JSON response parsing."""
    response_data = {
        "content": [
            {
                "type": "tool_use",
                "id": "tool_001",
                "name": "Write",
                "input": {"file_path": "test.py", "content": "print('test')"},
            }
        ]
    }
    resp_body = json.dumps(response_data).encode()

    with structlog.testing.capture_logs() as logs:
        actions = await claude_code_adapter.intercept_response(resp_body)

    assert len(actions) == 1

    events = [entry["event"] for entry in logs]
    # parse start log: "parsing response as JSON"
    assert any("parsing response" in e or "JSON" in e for e in events)
    # parse end log: "parsed 1 tool_use blocks from response"
    assert any("tool_use" in e or "1" in e for e in events)
    # performance log
    assert any("intercept_response" in e and "ms" in e for e in events)


@pytest.mark.asyncio
async def test_intercept_response_invalid_json_logs_error(claude_code_adapter):
    """Verify logging when response body is not JSON."""
    with structlog.testing.capture_logs() as logs:
        actions = await claude_code_adapter.intercept_response(b"not json")

    assert actions == []

    events = [entry["event"] for entry in logs]
    assert any("skipping" in e or "not JSON" in e or "not json" in e.lower() for e in events)
