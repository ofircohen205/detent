"""Tests for Codex hook adapter (Point 2 enforcement)."""

import json
from unittest.mock import MagicMock

import pytest
from aiohttp import web

from detent.adapters.hook.codex import CodexHookAdapter
from detent.pipeline.result import Finding, VerificationResult
from detent.schema import ActionType, AgentAction


@pytest.mark.asyncio
async def test_intercept_flat_format_create_file():
    """Parses flat OpenAI-style hook payload (name + arguments)."""
    adapter = CodexHookAdapter(session_manager=MagicMock())

    raw_event = {
        "name": "create_file",
        "arguments": json.dumps({"file_path": "/src/main.py", "content": "x = 1"}),
        "call_id": "call_hook_01",
        "session_id": "sess_abc",
    }

    action = await adapter.intercept(raw_event)

    assert action is not None
    assert action.agent == "codex"
    assert action.tool_name == "create_file"
    assert action.action_type == ActionType.FILE_WRITE
    assert action.tool_call_id == "call_hook_01"
    assert action.session_id == "sess_abc"
    assert action.tool_input["file_path"] == "/src/main.py"


@pytest.mark.asyncio
async def test_intercept_nested_function_format():
    """Parses nested OpenAI function format: {function: {name, arguments}, id}."""
    adapter = CodexHookAdapter(session_manager=MagicMock())

    raw_event = {
        "function": {
            "name": "run_command",
            "arguments": json.dumps({"command": "pytest tests/"}),
        },
        "id": "call_hook_02",
    }

    action = await adapter.intercept(raw_event)

    assert action is not None
    assert action.tool_name == "run_command"
    assert action.action_type == ActionType.SHELL_EXEC
    assert action.tool_call_id == "call_hook_02"
    assert action.tool_input["command"] == "pytest tests/"


@pytest.mark.asyncio
async def test_intercept_with_type_field():
    """Parses flat payload that includes a type field (Responses API style)."""
    adapter = CodexHookAdapter(session_manager=MagicMock())

    raw_event = {
        "type": "function_call",
        "name": "create_file",
        "arguments": json.dumps({"file_path": "/src/app.py", "content": ""}),
        "call_id": "call_hook_03",
    }

    action = await adapter.intercept(raw_event)

    assert action is not None
    assert action.action_type == ActionType.FILE_WRITE
    assert action.tool_call_id == "call_hook_03"


@pytest.mark.asyncio
async def test_intercept_dict_arguments():
    """Handles arguments provided as a dict (not JSON-encoded string)."""
    adapter = CodexHookAdapter(session_manager=MagicMock())

    raw_event = {
        "name": "create_file",
        "arguments": {"file_path": "/src/direct.py", "content": "y = 2"},
        "call_id": "call_hook_04",
    }

    action = await adapter.intercept(raw_event)

    assert action is not None
    assert action.tool_input["file_path"] == "/src/direct.py"


@pytest.mark.asyncio
async def test_intercept_missing_name_returns_none():
    """Returns None when tool name is absent."""
    adapter = CodexHookAdapter(session_manager=MagicMock())

    action = await adapter.intercept({"arguments": "{}", "call_id": "call_hook_05"})

    assert action is None


@pytest.mark.asyncio
async def test_intercept_unknown_tool_defaults_to_mcp_tool():
    """Unknown tools default to mcp_tool action type."""
    adapter = CodexHookAdapter(session_manager=MagicMock())

    action = await adapter.intercept({"name": "some_custom_tool", "arguments": "{}", "call_id": "call_hook_06"})

    assert action is not None
    assert action.action_type == ActionType.MCP_TOOL


@pytest.mark.asyncio
async def test_handle_verification_result_allow_on_pass():
    """Returns approved=True when verification passes."""
    adapter = CodexHookAdapter(session_manager=MagicMock())
    action = AgentAction(
        action_type="file_write",
        agent="codex",
        tool_name="create_file",
        tool_input={"file_path": "/src/main.py", "content": "x = 1"},
        tool_call_id="call_hook_07",
        session_id="sess_1",
        checkpoint_ref="chk_000",
        risk_level="medium",
    )
    result = VerificationResult(stage="pipeline", passed=True, findings=[], duration_ms=40.0)

    output = await adapter.handle_verification_result(action, result)

    assert output == {"approved": True, "decision": "allow"}


@pytest.mark.asyncio
async def test_handle_verification_result_deny_on_error():
    """Returns approved=False when verification has an error finding."""
    adapter = CodexHookAdapter(session_manager=MagicMock())
    action = AgentAction(
        action_type="file_write",
        agent="codex",
        tool_name="create_file",
        tool_input={"file_path": "/src/main.py", "content": "x ="},
        tool_call_id="call_hook_08",
        session_id="sess_1",
        checkpoint_ref="chk_001",
        risk_level="medium",
    )
    result = VerificationResult(
        stage="pipeline",
        passed=False,
        findings=[Finding(severity="error", file="/src/main.py", line=1, message="SyntaxError", stage="syntax")],
        duration_ms=25.0,
    )

    output = await adapter.handle_verification_result(action, result)

    assert output == {"approved": False, "decision": "deny"}


@pytest.mark.asyncio
async def test_handle_verification_result_allow_on_warning_only():
    """Warning-only findings still allow execution."""
    adapter = CodexHookAdapter(session_manager=MagicMock())
    action = AgentAction(
        action_type="file_write",
        agent="codex",
        tool_name="create_file",
        tool_input={"file_path": "/src/main.py", "content": "x = 1"},
        tool_call_id="call_hook_09",
        session_id="sess_1",
        checkpoint_ref="chk_002",
        risk_level="medium",
    )
    result = VerificationResult(
        stage="pipeline",
        passed=False,
        findings=[Finding(severity="warning", file="/src/main.py", line=1, message="line too long", stage="lint")],
        duration_ms=15.0,
    )

    output = await adapter.handle_verification_result(action, result)

    assert output == {"approved": True, "decision": "allow"}


def test_hook_adapter_route_and_name():
    """Hook adapter has expected route and agent name."""
    adapter = CodexHookAdapter(session_manager=MagicMock())
    assert adapter.route == "/hooks/codex"
    assert adapter.agent_name == "codex"


def test_hook_adapter_registers_on_app():
    """register() adds a POST route to the aiohttp app."""
    adapter = CodexHookAdapter(session_manager=MagicMock())
    app = web.Application()
    adapter.register(app)

    routes = [r for r in app.router.routes() if r.method == "POST"]
    paths = [r.resource.canonical for r in routes]
    assert "/hooks/codex" in paths
