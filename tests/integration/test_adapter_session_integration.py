"""Integration tests for adapters with SessionManager.

Tests the full flow of adapters intercepting tool calls,
normalizing them, and delegating to SessionManager for verification.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from detent.adapters.claude_code import ClaudeCodeAdapter
from detent.adapters.langgraph import LangGraphAdapter
from detent.checkpoint.engine import CheckpointEngine
from detent.config import PipelineConfig
from detent.ipc.channel import IPCControlChannel
from detent.pipeline.pipeline import VerificationPipeline
from detent.proxy.session import SessionManager
from detent.schema import ActionType
from detent.stages.syntax import SyntaxStage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
async def checkpoint_engine(tmp_path: Path) -> AsyncIterator[CheckpointEngine]:
    """Create a CheckpointEngine with shadow git."""
    shadow_git_dir = tmp_path / "shadow-git"
    engine = CheckpointEngine(shadow_git_path=shadow_git_dir)
    yield engine


@pytest.fixture
async def ipc_channel() -> AsyncIterator[IPCControlChannel]:
    """Create an IPC control channel."""
    channel = IPCControlChannel()
    await channel.start_server()
    yield channel
    await channel.stop_server()


@pytest.fixture
async def verification_pipeline() -> AsyncIterator[VerificationPipeline]:
    """Create a verification pipeline with syntax stage."""
    config = PipelineConfig(parallel=False, fail_fast=True, stages=[])
    pipeline = VerificationPipeline(stages=[SyntaxStage()], config=config)
    yield pipeline


@pytest.fixture
async def session_manager(
    checkpoint_engine: CheckpointEngine,
    verification_pipeline: VerificationPipeline,
    ipc_channel: IPCControlChannel,
) -> AsyncIterator[SessionManager]:
    """Create a session manager."""
    manager = SessionManager(
        checkpoint_engine=checkpoint_engine,
        pipeline=verification_pipeline,
        ipc_channel=ipc_channel,
    )
    yield manager


@pytest.mark.asyncio
async def test_claude_code_adapter_intercepts_and_normalizes(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test ClaudeCodeAdapter intercepts tool calls and normalizes to AgentAction."""
    adapter = ClaudeCodeAdapter(session_manager=session_manager)

    # Simulate a raw Claude Code tool call event
    raw_event = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp_path / "main.py"),
            "content": 'print("hello")\n',
        },
        "tool_call_id": "toolu_01ABC123",
    }

    # Intercept and normalize
    action = await adapter.intercept(raw_event)

    # Verify normalization
    assert action.action_type == ActionType.FILE_WRITE
    assert action.agent == "claude-code"
    assert action.tool_name == "Write"
    assert action.tool_input["file_path"] == str(tmp_path / "main.py")
    assert action.tool_input["content"] == 'print("hello")\n'
    assert action.tool_call_id == "toolu_01ABC123"


@pytest.mark.asyncio
async def test_claude_code_adapter_with_session_manager_valid_syntax(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test ClaudeCodeAdapter integrates with SessionManager for valid code."""
    adapter = ClaudeCodeAdapter(session_manager=session_manager)

    # Create test file
    test_file = tmp_path / "main.py"
    test_file.write_text('print("original")\n')

    # Start session
    session_id = "sess_claude_code_valid"
    await session_manager.start_session(session_id)

    try:
        # Simulate Claude Code hook
        raw_event = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(test_file),
                "content": 'print("hello")\nx = 42\n',
            },
            "tool_call_id": "toolu_01ABC123",
        }

        # Intercept and normalize
        action = await adapter.intercept(raw_event)
        action.session_id = session_id

        # Write the new content
        test_file.write_text(action.tool_input["content"])

        # Verify through SessionManager
        result = await session_manager.intercept_tool_call(action)

        # Should pass (valid Python)
        assert result.passed is True
        assert len(result.findings) == 0

    finally:
        await session_manager.end_session()


@pytest.mark.asyncio
async def test_claude_code_adapter_with_session_manager_invalid_syntax(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test ClaudeCodeAdapter integrates with SessionManager for invalid code."""
    adapter = ClaudeCodeAdapter(session_manager=session_manager)

    # Create test file
    test_file = tmp_path / "broken.py"
    test_file.write_text("x = 1\n")

    # Start session
    session_id = "sess_claude_code_invalid"
    await session_manager.start_session(session_id)

    try:
        # Simulate Claude Code hook with invalid syntax
        raw_event = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(test_file),
                "content": "def broken(:\n",
            },
            "tool_call_id": "toolu_01DEF456",
        }

        # Intercept and normalize
        action = await adapter.intercept(raw_event)
        action.session_id = session_id

        # Write the new content (invalid)
        test_file.write_text(action.tool_input["content"])

        # Verify through SessionManager
        result = await session_manager.intercept_tool_call(action)

        # Should fail (invalid Python)
        assert result.passed is False
        assert len(result.findings) > 0

    finally:
        await session_manager.end_session()


@pytest.mark.asyncio
async def test_langgraph_adapter_intercepts_and_normalizes(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test LangGraphAdapter intercepts tool calls and normalizes to AgentAction."""
    adapter = LangGraphAdapter(session_manager=session_manager)

    # Simulate a raw LangGraph tool call event
    raw_event = {
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(tmp_path / "utils.py"),
            "content": "def add(a, b):\n    return a + b\n",
        },
        "tool_call_id": "call_01XYZ789",
    }

    # Intercept and normalize
    action = await adapter.intercept(raw_event)

    # Verify normalization
    assert action.action_type == ActionType.FILE_WRITE
    assert action.agent == "langgraph"
    assert action.tool_name == "Write"
    assert action.tool_input["file_path"] == str(tmp_path / "utils.py")
    assert action.tool_input["content"] == "def add(a, b):\n    return a + b\n"
    assert action.tool_call_id == "call_01XYZ789"


@pytest.mark.asyncio
async def test_langgraph_adapter_with_session_manager_valid_code(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test LangGraphAdapter integrates with SessionManager for valid code."""
    adapter = LangGraphAdapter(session_manager=session_manager)

    # Create test file
    test_file = tmp_path / "utils.py"
    test_file.write_text("def subtract(a, b):\n    return a - b\n")

    # Start session
    session_id = "sess_langgraph_valid"
    await session_manager.start_session(session_id)

    try:
        # Simulate LangGraph tool call
        raw_event = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(test_file),
                "content": "def add(a, b):\n    return a + b\ndef subtract(a, b):\n    return a - b\n",
            },
            "tool_call_id": "call_01XYZ789",
        }

        # Intercept and normalize
        action = await adapter.intercept(raw_event)
        action.session_id = session_id

        # Write the new content
        test_file.write_text(action.tool_input["content"])

        # Verify through SessionManager
        result = await session_manager.intercept_tool_call(action)

        # Should pass (valid Python)
        assert result.passed is True
        assert len(result.findings) == 0

    finally:
        await session_manager.end_session()


@pytest.mark.asyncio
async def test_langgraph_adapter_with_session_manager_invalid_code(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test LangGraphAdapter integrates with SessionManager for invalid code."""
    adapter = LangGraphAdapter(session_manager=session_manager)

    # Create test file
    test_file = tmp_path / "code.py"
    test_file.write_text("x = 1\n")

    # Start session
    session_id = "sess_langgraph_invalid"
    await session_manager.start_session(session_id)

    try:
        # Simulate LangGraph tool call with invalid syntax
        raw_event = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(test_file),
                "content": "if True\n    print('missing colon')\n",
            },
            "tool_call_id": "call_02BAD123",
        }

        # Intercept and normalize
        action = await adapter.intercept(raw_event)
        action.session_id = session_id

        # Write the new content (invalid)
        test_file.write_text(action.tool_input["content"])

        # Verify through SessionManager
        result = await session_manager.intercept_tool_call(action)

        # Should fail (invalid Python)
        assert result.passed is False
        assert len(result.findings) > 0

    finally:
        await session_manager.end_session()


@pytest.mark.asyncio
async def test_adapter_normalizes_different_tool_types(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test that adapters properly normalize different tool types."""
    adapter = ClaudeCodeAdapter(session_manager=session_manager)

    # Test Edit tool
    edit_event = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": str(tmp_path / "file.py"),
            "content": "new content\n",
        },
        "tool_call_id": "toolu_edit_001",
    }

    action = await adapter.intercept(edit_event)
    assert action.action_type == ActionType.FILE_WRITE  # Edit is also FILE_WRITE
    assert action.tool_name == "Edit"

    # Test Bash tool
    bash_event = {
        "tool_name": "Bash",
        "tool_input": {"command": "ls -la"},
        "tool_call_id": "toolu_bash_001",
    }

    action = await adapter.intercept(bash_event)
    assert action.action_type == ActionType.SHELL_EXEC
    assert action.tool_name == "Bash"

    # Test Read tool
    read_event = {
        "tool_name": "Read",
        "tool_input": {"file_path": str(tmp_path / "file.py")},
        "tool_call_id": "toolu_read_001",
    }

    action = await adapter.intercept(read_event)
    assert action.action_type == ActionType.FILE_READ
    assert action.tool_name == "Read"


@pytest.mark.asyncio
async def test_adapter_checkpoint_ref_updated_by_session_manager(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test that SessionManager updates action checkpoint_ref."""
    adapter = ClaudeCodeAdapter(session_manager=session_manager)

    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("x = 1\n")

    # Start session
    session_id = "sess_checkpoint_update"
    await session_manager.start_session(session_id)

    try:
        # Intercept tool call (checkpoint_ref is empty initially)
        raw_event = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(test_file),
                "content": "x = 2\n",
            },
            "tool_call_id": "toolu_001",
        }

        action = await adapter.intercept(raw_event)
        assert action.checkpoint_ref == ""  # Not set yet

        action.session_id = session_id
        test_file.write_text(action.tool_input["content"])

        # Run through SessionManager
        await session_manager.intercept_tool_call(action)

        # After intercept_tool_call, action.checkpoint_ref should be set
        assert action.checkpoint_ref != ""
        assert action.checkpoint_ref.startswith("chk_before_write_")

    finally:
        await session_manager.end_session()


@pytest.mark.asyncio
async def test_multiple_tool_calls_in_sequence(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test multiple tool calls from adapters in sequence within one session."""
    claude_adapter = ClaudeCodeAdapter(session_manager=session_manager)
    langgraph_adapter = LangGraphAdapter(session_manager=session_manager)

    # Create test files
    file1 = tmp_path / "file1.py"
    file2 = tmp_path / "file2.py"
    file1.write_text("# file1\n")
    file2.write_text("# file2\n")

    # Start session
    session_id = "sess_multi_calls"
    await session_manager.start_session(session_id)

    try:
        # First tool call via Claude Code adapter
        raw_event1 = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(file1),
                "content": "# file1 modified\n",
            },
            "tool_call_id": "toolu_001",
        }

        action1 = await claude_adapter.intercept(raw_event1)
        action1.session_id = session_id
        file1.write_text(action1.tool_input["content"])

        result1 = await session_manager.intercept_tool_call(action1)
        assert result1.passed is True

        # Second tool call via LangGraph adapter
        raw_event2 = {
            "tool_name": "Write",
            "tool_input": {
                "file_path": str(file2),
                "content": "# file2 modified\n",
            },
            "tool_call_id": "call_002",
        }

        action2 = await langgraph_adapter.intercept(raw_event2)
        action2.session_id = session_id
        file2.write_text(action2.tool_input["content"])

        result2 = await session_manager.intercept_tool_call(action2)
        assert result2.passed is True

        # Verify both checkpoints were created
        assert len(session_manager._checkpoint_refs) == 2
        assert session_manager._checkpoint_refs[0].startswith("chk_before_write_")
        assert session_manager._checkpoint_refs[1].startswith("chk_before_write_")

    finally:
        await session_manager.end_session()
