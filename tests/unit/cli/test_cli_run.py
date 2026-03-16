"""Test detent run command."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from click.testing import CliRunner


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

        passed, _ = await run_file(str(temp_file), config, session)

    assert passed is True


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

        passed, _ = await run_file(str(temp_file), config, session)

        # Should have called rollback
        mock_checkpoint_instance.rollback.assert_called_once()
    assert passed is False


def test_run_dry_run_skips_checkpoint(tmp_path):
    """--dry-run should not create a checkpoint."""
    from detent.cli import run_file

    temp_file = tmp_path / "test.py"
    temp_file.write_text("x = 1")
    session = {"session_id": "sess_test", "checkpoints": []}

    with (
        patch("detent.cli.run.VerificationPipeline.from_config") as mock_pipeline,
        patch("detent.cli.run.CheckpointEngine") as mock_chk,
    ):
        mock_result = MagicMock(passed=True, findings=[])
        mock_pipeline.return_value.run = AsyncMock(return_value=mock_result)

        config = MagicMock(policy="standard")
        asyncio.run(run_file(str(temp_file), config, session, dry_run=True))

        mock_chk.return_value.savepoint.assert_not_called()
    assert session["checkpoints"] == []


def test_run_stage_filter_calls_only_named_stage(tmp_path):
    """--stage should filter pipeline to named stages only."""
    from detent.cli import run_file

    temp_file = tmp_path / "test.py"
    temp_file.write_text("x = 1")
    session = {"session_id": "sess_test", "checkpoints": []}

    with (
        patch("detent.cli.run.VerificationPipeline.from_config") as mock_pipeline,
        patch("detent.cli.run.CheckpointEngine") as mock_chk,
    ):
        mock_result = MagicMock(passed=True, findings=[])
        mock_pipeline.return_value.run = AsyncMock(return_value=mock_result)
        mock_chk.return_value.savepoint = AsyncMock()

        stage_syntax = MagicMock()
        stage_syntax.name = "syntax"
        stage_syntax.enabled = True
        stage_lint = MagicMock()
        stage_lint.name = "lint"
        stage_lint.enabled = True
        stage_tc = MagicMock()
        stage_tc.name = "typecheck"
        stage_tc.enabled = True
        config = MagicMock(policy="standard")
        config.pipeline.stages = [stage_syntax, stage_lint, stage_tc]

        asyncio.run(run_file(str(temp_file), config, session, stage_filter=("syntax",)))

        modified_config = mock_pipeline.call_args[0][0]
        enabled = [s.name for s in modified_config.pipeline.stages if s.enabled]
        assert enabled == ["syntax"]


def test_run_unknown_stage_exits_1(tmp_path):
    """--stage unknown-stage should exit 1 with error message."""
    from detent.cli import main

    runner = CliRunner()
    temp_file = tmp_path / "test.py"
    temp_file.write_text("x = 1")

    with patch("detent.cli.run.DetentConfig") as mock_load:
        mock_load.load.return_value = MagicMock(
            policy="standard",
            pipeline=MagicMock(stages=[MagicMock(name="syntax", enabled=True)]),
            get_enabled_stages=lambda: [],
        )
        result = runner.invoke(main, ["run", str(temp_file), "--stage", "nonexistent"])

    assert result.exit_code == 1
    assert "Unknown stage" in result.output
