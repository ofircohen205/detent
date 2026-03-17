"""Tests for detent run --json output."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner


def test_run_json_output_is_valid_json(tmp_path):
    """--json flag should output valid JSON with expected fields."""
    from detent.cli import main

    runner = CliRunner(mix_stderr=False)
    temp_file = tmp_path / "test.py"
    temp_file.write_text("x = 1")

    with (
        patch("detent.cli.run.DetentConfig") as mock_load,
        patch("detent.cli.run.VerificationPipeline.from_config") as mock_pipeline,
        patch("detent.cli.run.CheckpointEngine") as mock_chk,
    ):
        mock_config = MagicMock(policy="standard")
        mock_config.pipeline.stages = []
        mock_load.load.return_value = mock_config

        mock_result = MagicMock(passed=True, findings=[], stage="pipeline", duration_ms=12.5, metadata={})
        mock_pipeline.return_value.run = AsyncMock(return_value=mock_result)
        mock_chk.return_value.savepoint = AsyncMock()

        result = runner.invoke(main, ["run", str(temp_file), "--json"])

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["passed"] is True
    assert output["file"] == str(temp_file)
    assert output["stage"] == "pipeline"
    assert isinstance(output["findings"], list)


def test_run_json_error_for_missing_file(tmp_path):
    """--json should emit error object and exit 1 for missing file."""
    from detent.cli import main

    missing = tmp_path / "missing.py"
    runner = CliRunner(mix_stderr=False)
    result = runner.invoke(main, ["run", str(missing), "--json"])

    assert result.exit_code == 1
    output = json.loads(result.output)
    assert output["passed"] is False
    assert "error" in output


def test_run_json_includes_rollback_failed(tmp_path):
    """--json output should include rollback_failed when rollback fails."""
    from detent.cli import main

    temp_file = tmp_path / "test.py"
    temp_file.write_text("x = 1")
    runner = CliRunner(mix_stderr=False)

    with (
        patch("detent.cli.run.DetentConfig") as mock_load,
        patch("detent.cli.run.VerificationPipeline.from_config") as mock_pipeline,
        patch("detent.cli.run.CheckpointEngine") as mock_chk,
    ):
        mock_config = MagicMock(policy="standard")
        mock_config.pipeline.stages = []
        mock_load.load.return_value = mock_config

        mock_result = MagicMock(
            passed=False,
            findings=[
                MagicMock(
                    severity="error",
                    file=str(temp_file),
                    line=1,
                    column=1,
                    message="boom",
                    code="E000",
                    stage="syntax",
                    fix_suggestion=None,
                )
            ],
            stage="pipeline",
            duration_ms=10.0,
            metadata={},
        )
        mock_pipeline.return_value.run = AsyncMock(return_value=mock_result)
        mock_chk.return_value.savepoint = AsyncMock()
        mock_chk.return_value.rollback = AsyncMock(side_effect=RuntimeError("boom"))

        result = runner.invoke(main, ["run", str(temp_file), "--json"])

    assert result.exit_code == 1
    output = json.loads(result.output)
    assert output["rollback_failed"] is True
