"""Tests for session manager."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from detent.checkpoint.engine import CheckpointEngine
from detent.pipeline.pipeline import VerificationPipeline
from detent.pipeline.result import VerificationResult
from detent.proxy.session import SessionManager
from detent.proxy.types import DetentSessionConflictError, IPCMessageType
from detent.schema import ActionType, AgentAction, RiskLevel


@pytest.mark.asyncio
async def test_session_lifecycle():
    """SessionManager should manage start, active, and end states."""
    checkpoint_engine = CheckpointEngine()
    pipeline = MagicMock(spec=VerificationPipeline)
    ipc_channel = AsyncMock()

    manager = SessionManager(
        checkpoint_engine=checkpoint_engine,
        pipeline=pipeline,
        ipc_channel=ipc_channel,
    )

    # Initially not active
    assert manager.is_active is False
    assert manager.session_id is None

    # Start session
    await manager.start_session("sess_123")
    assert manager.is_active is True
    assert manager.session_id == "sess_123"

    # Verify SESSION_START message was sent
    ipc_channel.send_message.assert_called()
    call_args = ipc_channel.send_message.call_args[0][0]
    assert call_args.type == IPCMessageType.SESSION_START
    assert call_args.data["session_id"] == "sess_123"

    # Try to start another session (should fail)
    with pytest.raises(DetentSessionConflictError):
        await manager.start_session("sess_456")

    # End session
    await manager.end_session()
    assert manager.is_active is False
    assert manager.session_id is None

    # Verify SESSION_END message was sent
    assert ipc_channel.send_message.call_count == 2


@pytest.mark.asyncio
async def test_intercept_tool_call_creates_checkpoint():
    """Intercepting tool call should create SAVEPOINT."""
    checkpoint_engine = CheckpointEngine()
    pipeline = MagicMock(spec=VerificationPipeline)
    ipc_channel = AsyncMock()

    manager = SessionManager(
        checkpoint_engine=checkpoint_engine,
        pipeline=pipeline,
        ipc_channel=ipc_channel,
    )

    await manager.start_session("sess_123")

    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "print('hello')"},
        tool_call_id="toolu_123",
        session_id="sess_123",
        checkpoint_ref="",
        risk_level=RiskLevel.MEDIUM,
    )

    # Mock pipeline result (pass)
    pipeline.run = AsyncMock(
        return_value=VerificationResult(
            stage="pipeline",
            passed=True,
            findings=[],
            duration_ms=10.0,
        )
    )

    result = await manager.intercept_tool_call(action)

    # Verify checkpoint was created
    savepoints = await checkpoint_engine.list_savepoints()
    assert len(savepoints) > 0
    assert savepoints[0].startswith("chk_before_write_")

    # Verify pipeline was called
    pipeline.run.assert_called_once()

    # Verify action checkpoint_ref was updated
    called_action = pipeline.run.call_args[0][0]
    assert called_action.checkpoint_ref.startswith("chk_before_write_")

    # Verify result is passed through
    assert result.passed is True

    # Verify IPC messages were sent
    # SESSION_START + TOOL_INTERCEPTED + VERIFICATION_RESULT (for pass)
    assert ipc_channel.send_message.call_count >= 3

    await manager.end_session()


@pytest.mark.asyncio
async def test_intercept_tool_call_fails_and_rolls_back():
    """Verification failure should trigger rollback."""
    checkpoint_engine = CheckpointEngine()
    pipeline = MagicMock(spec=VerificationPipeline)
    ipc_channel = AsyncMock()

    manager = SessionManager(
        checkpoint_engine=checkpoint_engine,
        pipeline=pipeline,
        ipc_channel=ipc_channel,
    )

    await manager.start_session("sess_123")

    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "invalid syntax"},
        tool_call_id="toolu_456",
        session_id="sess_123",
        checkpoint_ref="",
        risk_level=RiskLevel.MEDIUM,
    )

    # Mock pipeline result (failure)
    from detent.pipeline.result import Finding

    pipeline.run = AsyncMock(
        return_value=VerificationResult(
            stage="pipeline",
            passed=False,
            findings=[
                Finding(
                    severity="error",
                    file="/src/main.py",
                    line=1,
                    message="Syntax error",
                    code="E0001",
                    stage="syntax",
                )
            ],
            duration_ms=10.0,
        )
    )

    result = await manager.intercept_tool_call(action)

    # Verify result is failure
    assert result.passed is False

    # Verify rollback instruction was sent
    ipc_calls = [call[0][0] for call in ipc_channel.send_message.call_args_list]
    rollback_msgs = [m for m in ipc_calls if m.type == IPCMessageType.ROLLBACK_INSTRUCTION]
    assert len(rollback_msgs) > 0
    assert rollback_msgs[0].data["tool_call_id"] == "toolu_456"

    await manager.end_session()


@pytest.mark.asyncio
async def test_tool_call_without_active_session():
    """Tool call without active session should fail safely."""
    checkpoint_engine = CheckpointEngine()
    pipeline = MagicMock(spec=VerificationPipeline)
    ipc_channel = AsyncMock()

    manager = SessionManager(
        checkpoint_engine=checkpoint_engine,
        pipeline=pipeline,
        ipc_channel=ipc_channel,
    )

    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "print('hello')"},
        tool_call_id="toolu_789",
        session_id="sess_none",
        checkpoint_ref="",
        risk_level=RiskLevel.MEDIUM,
    )

    result = await manager.intercept_tool_call(action)

    # Should return safe failure result
    assert result.passed is False
    assert result.stage == "session"


@pytest.mark.asyncio
async def test_multiple_tool_calls_same_session():
    """Multiple tool calls should create separate checkpoints."""
    checkpoint_engine = CheckpointEngine()
    pipeline = MagicMock(spec=VerificationPipeline)
    ipc_channel = AsyncMock()

    manager = SessionManager(
        checkpoint_engine=checkpoint_engine,
        pipeline=pipeline,
        ipc_channel=ipc_channel,
    )

    await manager.start_session("sess_multi")

    # Mock pipeline result (always pass)
    pipeline.run = AsyncMock(
        return_value=VerificationResult(
            stage="pipeline",
            passed=True,
            findings=[],
            duration_ms=10.0,
        )
    )

    # First tool call
    action1 = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": "/src/a.py", "content": "a = 1"},
        tool_call_id="toolu_a",
        session_id="sess_multi",
        checkpoint_ref="",
        risk_level=RiskLevel.MEDIUM,
    )

    result1 = await manager.intercept_tool_call(action1)
    assert result1.passed is True

    # Second tool call
    action2 = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": "/src/b.py", "content": "b = 2"},
        tool_call_id="toolu_b",
        session_id="sess_multi",
        checkpoint_ref="",
        risk_level=RiskLevel.MEDIUM,
    )

    result2 = await manager.intercept_tool_call(action2)
    assert result2.passed is True

    # Verify separate checkpoints were created
    savepoints = await checkpoint_engine.list_savepoints()
    assert len(savepoints) == 2
    assert savepoints[0] == "chk_before_write_000"
    assert savepoints[1] == "chk_before_write_001"

    await manager.end_session()


@pytest.mark.asyncio
async def test_concurrent_session_operations():
    """SessionManager should handle concurrent operations with locking."""
    checkpoint_engine = CheckpointEngine()
    pipeline = MagicMock(spec=VerificationPipeline)
    ipc_channel = AsyncMock()

    manager = SessionManager(
        checkpoint_engine=checkpoint_engine,
        pipeline=pipeline,
        ipc_channel=ipc_channel,
    )

    # Mock pipeline result (always pass)
    pipeline.run = AsyncMock(
        return_value=VerificationResult(
            stage="pipeline",
            passed=True,
            findings=[],
            duration_ms=10.0,
        )
    )

    await manager.start_session("sess_concurrent")

    # Create multiple tool calls concurrently
    actions = [
        AgentAction(
            action_type=ActionType.FILE_WRITE,
            agent="claude-code",
            tool_name="Write",
            tool_input={"file_path": f"/src/file{i}.py", "content": f"x = {i}"},
            tool_call_id=f"toolu_{i}",
            session_id="sess_concurrent",
            checkpoint_ref="",
            risk_level=RiskLevel.MEDIUM,
        )
        for i in range(5)
    ]

    results = await asyncio.gather(*[manager.intercept_tool_call(action) for action in actions])

    # All should pass
    assert all(r.passed for r in results)

    # Verify all checkpoints were created
    savepoints = await checkpoint_engine.list_savepoints()
    assert len(savepoints) == 5

    await manager.end_session()
