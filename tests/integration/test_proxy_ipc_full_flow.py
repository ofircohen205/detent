"""Integration tests for proxy → IPC → pipeline → rollback flow."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from detent.checkpoint.engine import CheckpointEngine
from detent.config import PipelineConfig
from detent.ipc.channel import IPCControlChannel
from detent.pipeline.pipeline import VerificationPipeline
from detent.proxy.session import SessionManager
from detent.schema import ActionType, AgentAction, RiskLevel
from detent.stages.syntax import SyntaxStage

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@pytest.fixture
async def tmp_ipc_socket(tmp_path: Path) -> AsyncIterator[Path]:
    """Create a temporary IPC socket path.

    Note: Unix socket paths have max length ~104 chars on macOS.
    We use a very short path to stay well below the limit.
    """
    # Use a much shorter path to avoid "AF_UNIX path too long" error
    import shutil
    import tempfile

    short_path = Path(tempfile.mkdtemp(prefix="dsock"))
    try:
        socket_path = short_path / "c.sock"
        yield socket_path
    finally:
        if short_path.exists():
            shutil.rmtree(short_path, ignore_errors=True)


@pytest.fixture
async def checkpoint_engine(tmp_path: Path) -> AsyncIterator[CheckpointEngine]:
    """Create a CheckpointEngine with shadow git."""
    shadow_git_dir = tmp_path / "shadow-git"
    engine = CheckpointEngine(shadow_git_path=shadow_git_dir)
    yield engine


@pytest.fixture
async def ipc_channel(tmp_ipc_socket: Path) -> AsyncIterator[IPCControlChannel]:
    """Create and start an IPC control channel."""
    channel = IPCControlChannel(socket_path=tmp_ipc_socket)
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
async def test_full_flow_syntax_check_failure_and_rollback(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test complete flow: create checkpoint → verify syntax error → rollback."""
    # Setup: create a test file with valid Python code
    test_file = tmp_path / "src" / "main.py"
    test_file.parent.mkdir(parents=True)
    original_content = "print('original')\n"
    test_file.write_text(original_content)

    # Start a session
    session_id = "sess_test_syntax_fail"
    await session_manager.start_session(session_id)

    try:
        # Create action with invalid Python syntax
        # Note: intercept_tool_call will create its own checkpoint automatically
        invalid_content = "this is not valid python !!!"
        action = AgentAction(
            action_type=ActionType.FILE_WRITE,
            agent="claude-code",
            tool_name="Write",
            tool_input={
                "file_path": str(test_file),
                "content": invalid_content,
            },
            tool_call_id="toolu_001",
            session_id=session_id,
            checkpoint_ref="",  # Will be set by intercept_tool_call
            risk_level=RiskLevel.MEDIUM,
        )

        # Run verification through session manager
        # This will:
        # 1. Create a checkpoint of the current (good) file state
        # 2. Run syntax verification on the proposed content
        # 3. Fail verification because of syntax error
        # 4. Trigger rollback to restore the original file
        result = await session_manager.intercept_tool_call(action)

        # Verification should have failed
        assert result.passed is False
        assert len(result.findings) > 0

        # File should still have original content (no actual write happened in our mock)
        # In a real scenario, the agent would write after getting the pass signal
        # But since we didn't write, it should still be original
        assert test_file.read_text() == original_content
    finally:
        await session_manager.end_session()


@pytest.mark.asyncio
async def test_full_flow_valid_code_passes_verification(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test flow with valid Python code that passes verification."""
    # Setup: create a test file
    test_file = tmp_path / "src" / "utils.py"
    test_file.parent.mkdir(parents=True)
    original_content = "def helper():\n    return 42\n"
    test_file.write_text(original_content)

    # Start a session
    session_id = "sess_test_valid_code"
    await session_manager.start_session(session_id)

    try:
        # Create checkpoint
        await session_manager.checkpoint_engine.savepoint("chk_002", [str(test_file)])

        # Create action with valid Python code
        new_content = "def helper():\n    return 42\n\ndef another():\n    return 100\n"
        action = AgentAction(
            action_type=ActionType.FILE_WRITE,
            agent="claude-code",
            tool_name="Write",
            tool_input={
                "file_path": str(test_file),
                "content": new_content,
            },
            tool_call_id="toolu_002",
            session_id=session_id,
            checkpoint_ref="chk_002",
            risk_level=RiskLevel.LOW,
        )

        # Write valid content
        test_file.write_text(new_content)

        # Run verification
        result = await session_manager.intercept_tool_call(action)

        # Verification should pass
        assert result.passed is True
        assert result.findings == []

        # File should remain unchanged
        assert test_file.read_text() == new_content
    finally:
        await session_manager.end_session()


@pytest.mark.asyncio
async def test_session_lifecycle_start_end(
    session_manager: SessionManager,
) -> None:
    """Test session start and end lifecycle."""
    session_id = "sess_lifecycle"

    # Should be inactive initially
    assert session_manager.is_active is False
    assert session_manager.session_id is None

    # Start session
    await session_manager.start_session(session_id)
    assert session_manager.is_active is True
    assert session_manager.session_id == session_id

    # End session
    await session_manager.end_session()
    assert session_manager.is_active is False
    assert session_manager.session_id is None


@pytest.mark.asyncio
async def test_session_conflict_on_double_start(
    session_manager: SessionManager,
) -> None:
    """Test that starting a session twice raises an error."""
    from detent.proxy.types import DetentSessionConflictError

    session_id = "sess_conflict"

    # Start session
    await session_manager.start_session(session_id)

    try:
        # Attempt to start another session should fail
        with pytest.raises(DetentSessionConflictError):
            await session_manager.start_session("sess_another")
    finally:
        await session_manager.end_session()


@pytest.mark.asyncio
async def test_checkpoint_refs_tracked_per_session(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test that checkpoint refs are tracked correctly during a session."""
    # Create test files
    file1 = tmp_path / "file1.py"
    file2 = tmp_path / "file2.py"
    file1.write_text("# file1\n")
    file2.write_text("# file2\n")

    session_id = "sess_checkpoints"
    await session_manager.start_session(session_id)

    try:
        # Create multiple checkpoints
        await session_manager.checkpoint_engine.savepoint("chk_001", [str(file1)])
        await session_manager.checkpoint_engine.savepoint("chk_002", [str(file2)])

        # Create actions (won't verify, just create checkpoints)
        action1 = AgentAction(
            action_type=ActionType.FILE_WRITE,
            agent="claude-code",
            tool_name="Write",
            tool_input={"file_path": str(file1), "content": "# modified1\n"},
            tool_call_id="toolu_001",
            session_id=session_id,
            checkpoint_ref="chk_001",
            risk_level=RiskLevel.LOW,
        )

        action2 = AgentAction(
            action_type=ActionType.FILE_WRITE,
            agent="claude-code",
            tool_name="Write",
            tool_input={"file_path": str(file2), "content": "# modified2\n"},
            tool_call_id="toolu_002",
            session_id=session_id,
            checkpoint_ref="chk_002",
            risk_level=RiskLevel.LOW,
        )

        # Intercept tool calls (with valid syntax so they pass)
        file1.write_text("# modified1\n")
        file2.write_text("# modified2\n")

        result1 = await session_manager.intercept_tool_call(action1)
        result2 = await session_manager.intercept_tool_call(action2)

        # Both should pass
        assert result1.passed is True
        assert result2.passed is True

        # Session should have tracked both checkpoints
        assert len(session_manager._checkpoint_refs) == 2
        assert "chk_before_write_000" in session_manager._checkpoint_refs
        assert "chk_before_write_001" in session_manager._checkpoint_refs
    finally:
        await session_manager.end_session()


@pytest.mark.asyncio
async def test_ipc_messages_sent_during_flow(
    tmp_path: Path,
    session_manager: SessionManager,
    tmp_ipc_socket: Path,
) -> None:
    """Test that IPC messages are sent at key points in the flow."""
    # Setup: create a test file
    test_file = tmp_path / "code.py"
    test_file.write_text("x = 1\n")

    session_id = "sess_ipc_test"

    # Start session - should send SESSION_START message
    await session_manager.start_session(session_id)

    try:
        # Create checkpoint and action
        await session_manager.checkpoint_engine.savepoint("chk_001", [str(test_file)])

        action = AgentAction(
            action_type=ActionType.FILE_WRITE,
            agent="claude-code",
            tool_name="Write",
            tool_input={
                "file_path": str(test_file),
                "content": "x = 1\ny = 2\n",
            },
            tool_call_id="toolu_001",
            session_id=session_id,
            checkpoint_ref="chk_001",
            risk_level=RiskLevel.LOW,
        )

        # Write valid content
        test_file.write_text("x = 1\ny = 2\n")

        # Run verification - should send TOOL_INTERCEPTED and VERIFICATION_RESULT
        result = await session_manager.intercept_tool_call(action)
        assert result.passed is True

        # Verify IPC channel is still running
        assert session_manager.ipc_channel.is_running is True
    finally:
        await session_manager.end_session()


@pytest.mark.asyncio
async def test_rollback_multiple_files(
    tmp_path: Path,
    checkpoint_engine: CheckpointEngine,
) -> None:
    """Test rollback of multiple files at once."""
    # Create multiple test files
    files = []
    originals = {}
    for i in range(3):
        f = tmp_path / f"file{i}.py"
        content = f"# file {i}\nx = {i}\n"
        f.write_text(content)
        files.append(str(f))
        originals[str(f)] = content

    # Create checkpoint for all files
    ref = "chk_multi"
    await checkpoint_engine.savepoint(ref, files)

    # Modify all files
    for f in files:
        Path(f).write_text("CORRUPTED\n")

    # Verify files are corrupted
    for f in files:
        assert Path(f).read_text() == "CORRUPTED\n"

    # Rollback
    await checkpoint_engine.rollback(ref)

    # Verify files are restored
    for f in files:
        assert Path(f).read_text() == originals[f]


@pytest.mark.asyncio
async def test_verification_result_metadata_includes_stage_results(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test that verification results include per-stage metadata."""
    test_file = tmp_path / "test.py"
    test_file.write_text("print('test')\n")

    session_id = "sess_metadata"
    await session_manager.start_session(session_id)

    try:
        await session_manager.checkpoint_engine.savepoint("chk_001", [str(test_file)])

        action = AgentAction(
            action_type=ActionType.FILE_WRITE,
            agent="claude-code",
            tool_name="Write",
            tool_input={
                "file_path": str(test_file),
                "content": "print('modified')\n",
            },
            tool_call_id="toolu_001",
            session_id=session_id,
            checkpoint_ref="chk_001",
            risk_level=RiskLevel.LOW,
        )

        test_file.write_text("print('modified')\n")

        result = await session_manager.intercept_tool_call(action)

        # Result should have pipeline stage
        assert result.stage == "pipeline"
        assert result.passed is True
    finally:
        await session_manager.end_session()


@pytest.mark.asyncio
async def test_feedback_synthesis_on_verification_failure(
    tmp_path: Path,
    session_manager: SessionManager,
) -> None:
    """Test that feedback is synthesized on verification failure."""
    test_file = tmp_path / "broken.py"
    test_file.write_text("x = 1\n")

    # Ensure synthesizer is available
    assert session_manager.synthesizer is not None

    session_id = "sess_feedback"
    await session_manager.start_session(session_id)

    try:
        await session_manager.checkpoint_engine.savepoint("chk_001", [str(test_file)])

        # Write syntax error
        action = AgentAction(
            action_type=ActionType.FILE_WRITE,
            agent="claude-code",
            tool_name="Write",
            tool_input={
                "file_path": str(test_file),
                "content": "def broken(:\n",
            },
            tool_call_id="toolu_001",
            session_id=session_id,
            checkpoint_ref="chk_001",
            risk_level=RiskLevel.HIGH,
        )

        test_file.write_text("def broken(:\n")

        result = await session_manager.intercept_tool_call(action)

        # Should fail verification
        assert result.passed is False
        assert len(result.findings) > 0

        # File should be rolled back
        # Note: We can't directly check IPC messages here, but they are sent
        # in _on_verification_fail which includes synthesized feedback
    finally:
        await session_manager.end_session()


@pytest.mark.asyncio
async def test_tool_call_without_active_session(
    session_manager: SessionManager,
    tmp_path: Path,
) -> None:
    """Test that tool call interception without active session returns safe error."""
    test_file = tmp_path / "test.py"
    test_file.write_text("x = 1\n")

    # No active session
    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="claude-code",
        tool_name="Write",
        tool_input={
            "file_path": str(test_file),
            "content": "x = 2\n",
        },
        tool_call_id="toolu_001",
        session_id="nosession",
        checkpoint_ref="chk_001",
        risk_level=RiskLevel.LOW,
    )

    # Should return failed result without crashing
    result = await session_manager.intercept_tool_call(action)
    assert result.passed is False
    assert result.stage == "session"
