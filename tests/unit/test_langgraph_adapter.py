"""Tests for LangGraph adapter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from detent.adapters.langgraph import LangGraphAdapter
from detent.pipeline.result import Finding, VerificationResult
from detent.schema import ActionType, AgentAction


@pytest.mark.asyncio
async def test_langgraph_adapter_normalizes_action():
    """LangGraphAdapter should normalize LangGraph state to AgentAction."""
    adapter = LangGraphAdapter(session_manager=MagicMock())

    raw_event = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": "/src/main.py",
            "content": "def hello():\n    pass",
        },
        "tool_call_id": "call_123",
    }

    action = await adapter.intercept(raw_event)

    assert action.agent == "langgraph"
    assert action.tool_name == "Write"
    assert action.action_type == ActionType.FILE_WRITE
    assert action.tool_input["file_path"] == "/src/main.py"


@pytest.mark.asyncio
async def test_langgraph_adapter_maps_edit_tool():
    """LangGraphAdapter should map Edit tool to FILE_WRITE."""
    adapter = LangGraphAdapter(session_manager=MagicMock())

    raw_event = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/src/main.py",
            "old_string": "x = 1",
            "new_string": "x = 2",
        },
        "tool_call_id": "call_124",
    }

    action = await adapter.intercept(raw_event)

    assert action.action_type == ActionType.FILE_WRITE
    assert action.tool_name == "Edit"


@pytest.mark.asyncio
async def test_langgraph_adapter_maps_bash_tool():
    """LangGraphAdapter should map Bash tool to SHELL_EXEC."""
    adapter = LangGraphAdapter(session_manager=MagicMock())

    raw_event = {
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la"},
        "tool_call_id": "call_125",
    }

    action = await adapter.intercept(raw_event)

    assert action.action_type == ActionType.SHELL_EXEC
    assert action.tool_name == "Bash"


@pytest.mark.asyncio
async def test_langgraph_adapter_maps_unknown_tool_to_mcp():
    """LangGraphAdapter should map unknown tools to MCP_TOOL."""
    adapter = LangGraphAdapter(session_manager=MagicMock())

    raw_event = {
        "tool_name": "CustomTool",
        "tool_input": {"arg": "value"},
        "tool_call_id": "call_126",
    }

    action = await adapter.intercept(raw_event)

    assert action.action_type == ActionType.MCP_TOOL
    assert action.tool_name == "CustomTool"


@pytest.mark.asyncio
async def test_langgraph_adapter_allows_passing_verification():
    """LangGraphAdapter should allow tool when verification passes."""
    adapter = LangGraphAdapter(session_manager=MagicMock())

    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="langgraph",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "x = 1"},
        tool_call_id="call_1",
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
    assert output is None  # Allow


@pytest.mark.asyncio
async def test_langgraph_adapter_blocks_on_typecheck_error():
    """LangGraphAdapter should block on typecheck errors."""
    adapter = LangGraphAdapter(session_manager=MagicMock())

    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="langgraph",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "x: int = 'string'"},
        tool_call_id="call_1",
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
                message="Incompatible types in assignment",
                stage="typecheck",
            )
        ],
        duration_ms=150.0,
    )

    with pytest.raises(ValueError, match="Verification failed"):
        await adapter.handle_verification_result(action, result)


@pytest.mark.asyncio
async def test_langgraph_adapter_allows_warnings():
    """LangGraphAdapter should allow tool with warnings only."""
    adapter = LangGraphAdapter(session_manager=MagicMock())

    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="langgraph",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "import os\nx = 1"},
        tool_call_id="call_2",
        session_id="sess_1",
        checkpoint_ref="chk_2",
        risk_level="medium",
    )

    result = VerificationResult(
        stage="pipeline",
        passed=False,
        findings=[
            Finding(
                severity="warning",
                file="/src/main.py",
                line=1,
                message="Unused import: os",
                stage="lint",
            )
        ],
        duration_ms=100.0,
    )

    output = await adapter.handle_verification_result(action, result)
    assert output is None  # Allow despite warnings


@pytest.mark.asyncio
async def test_langgraph_adapter_blocks_on_syntax_error():
    """LangGraphAdapter should block on syntax errors."""
    adapter = LangGraphAdapter(session_manager=MagicMock())

    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="langgraph",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "def foo(\n"},
        tool_call_id="call_3",
        session_id="sess_1",
        checkpoint_ref="chk_3",
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
                message="SyntaxError: unexpected EOF while parsing",
                stage="syntax",
            )
        ],
        duration_ms=50.0,
    )

    with pytest.raises(ValueError, match="Verification failed"):
        await adapter.handle_verification_result(action, result)


@pytest.mark.asyncio
async def test_langgraph_adapter_blocks_on_multiple_errors():
    """LangGraphAdapter should block when multiple errors exist."""
    adapter = LangGraphAdapter(session_manager=MagicMock())

    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="langgraph",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "x: int = 'bad'"},
        tool_call_id="call_4",
        session_id="sess_1",
        checkpoint_ref="chk_4",
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
                message="Type error 1",
                stage="typecheck",
            ),
            Finding(
                severity="error",
                file="/src/main.py",
                line=1,
                message="Type error 2",
                stage="typecheck",
            ),
        ],
        duration_ms=100.0,
    )

    with pytest.raises(ValueError, match="2 error"):
        await adapter.handle_verification_result(action, result)


@pytest.mark.asyncio
async def test_langgraph_adapter_agent_name():
    """LangGraphAdapter should have correct agent_name."""
    adapter = LangGraphAdapter(session_manager=MagicMock())
    assert adapter.agent_name == "langgraph"
