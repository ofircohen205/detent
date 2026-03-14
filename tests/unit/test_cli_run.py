"""Test detent run command."""

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_run_file_passes():
    """run_file should pass when pipeline returns passed=True."""
    from detent.cli import run_file

    # Create temp file
    temp_file = Path("/tmp/test.py")
    temp_file.write_text("print('hello')")

    # Create valid session
    session = {
        "session_id": "sess_test123",
        "checkpoints": [],
        "started_at": "2026-03-08T00:00:00Z",
        "last_updated": "2026-03-08T00:00:00Z",
    }

    with (
        patch("detent.cli.run.VerificationPipeline.from_config") as mock_pipeline,
        patch("detent.cli.run.CheckpointEngine") as mock_chk_class,
    ):
        # Mock pipeline result
        mock_result = MagicMock()
        mock_result.passed = True
        mock_result.findings = []

        mock_pipeline_instance = AsyncMock()
        mock_pipeline_instance.run.return_value = mock_result
        mock_pipeline.return_value = mock_pipeline_instance

        # Mock checkpoint
        mock_checkpoint_instance = AsyncMock()
        mock_checkpoint_instance.savepoint = AsyncMock()
        mock_chk_class.return_value = mock_checkpoint_instance

        config = MagicMock()
        config.policy = "standard"

        result = await run_file(str(temp_file), config, session)

        assert result is True


@pytest.mark.asyncio
async def test_run_file_fails_and_rollsback():
    """run_file should rollback when pipeline returns passed=False."""
    from detent.cli import run_file

    temp_file = Path("/tmp/test.py")
    temp_file.write_text("invalid python syntax!")

    # Create valid session
    session = {
        "session_id": "sess_test123",
        "checkpoints": [],
        "started_at": "2026-03-08T00:00:00Z",
        "last_updated": "2026-03-08T00:00:00Z",
    }

    with (
        patch("detent.cli.run.VerificationPipeline.from_config") as mock_pipeline,
        patch("detent.cli.run.CheckpointEngine") as mock_chk_class,
    ):
        # Mock failed pipeline result
        mock_result = MagicMock()
        mock_result.passed = False
        mock_result.findings = [MagicMock(severity="error", message="Syntax error")]

        mock_pipeline_instance = AsyncMock()
        mock_pipeline_instance.run.return_value = mock_result
        mock_pipeline.return_value = mock_pipeline_instance

        # Mock checkpoint
        mock_checkpoint_instance = AsyncMock()
        mock_checkpoint_instance.savepoint = AsyncMock()
        mock_checkpoint_instance.rollback = AsyncMock()
        mock_chk_class.return_value = mock_checkpoint_instance

        config = MagicMock()
        config.policy = "standard"

        result = await run_file(str(temp_file), config, session)

        # Should have called rollback
        mock_checkpoint_instance.rollback.assert_called_once()
        assert result is False
