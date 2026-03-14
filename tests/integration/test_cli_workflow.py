"""Integration test for full CLI workflow.

Tests: detent init → detent run → detent status → detent rollback
"""

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_full_workflow(tmp_path):
    """Test complete workflow: init, run, status, rollback."""
    # Change to temp directory
    os.chdir(tmp_path)

    # Create a test Python file
    test_file = tmp_path / "src" / "main.py"
    test_file.parent.mkdir()
    test_file.write_text("print('hello world')\n")

    from detent.cli import SessionManager, run_file

    # Step 1: Initialize
    # (Skip interactive for testing, just create config manually)
    from detent.config import DetentConfig, PipelineConfig, StageConfig

    config = DetentConfig(
        agent="claude-code",
        policy="standard",
        pipeline=PipelineConfig(
            parallel=False,
            fail_fast=True,
            stages=[
                StageConfig(name="syntax", enabled=True),
                StageConfig(name="lint", enabled=True),
                StageConfig(name="typecheck", enabled=True, timeout=30),
                StageConfig(name="tests", enabled=True, timeout=60),
            ],
        ),
    )

    # Step 2: Create session
    mgr = SessionManager(tmp_path / ".detent" / "session")
    session = mgr.load_or_create()
    session["agent"] = "claude-code"
    mgr.save(session)

    # Verify session was created
    assert session["session_id"].startswith("sess_")
    assert len(session["checkpoints"]) == 0

    # Step 3: Mock pipeline and run
    with (
        patch("detent.cli.VerificationPipeline.from_config") as mock_pipeline,
        patch("detent.cli.CheckpointEngine") as mock_checkpoint,
    ):
        # Mock successful pipeline result
        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.findings = []

        mock_pipeline_instance = AsyncMock()
        mock_pipeline_instance.run.return_value = mock_result
        mock_pipeline.return_value = mock_pipeline_instance

        # Mock checkpoint
        mock_checkpoint_instance = AsyncMock()
        mock_checkpoint_instance.savepoint = AsyncMock()
        mock_checkpoint_instance.rollback = AsyncMock()
        mock_checkpoint.return_value = mock_checkpoint_instance

        # Run verification
        result = await run_file(str(test_file), config, session)

        assert result is True
        assert len(session["checkpoints"]) == 1
        assert session["checkpoints"][0]["ref"] == "chk_before_write_000"

        # Save session after successful run
        mgr.save(session)

    # Step 4: Verify status shows checkpoint
    session = mgr.load_or_create()
    assert len(session["checkpoints"]) > 0

    # Step 5: Mock rollback and verify
    with patch("detent.cli.rollback.CheckpointEngine") as mock_checkpoint:
        mock_checkpoint_instance = AsyncMock()
        mock_checkpoint_instance.rollback = AsyncMock()
        mock_checkpoint.return_value = mock_checkpoint_instance

        # This would be called by do_rollback
        from detent.cli import do_rollback

        await do_rollback("chk_before_write_000", yes=True)

        # Verify rollback was called
        mock_checkpoint_instance.rollback.assert_called_once_with("chk_before_write_000")
