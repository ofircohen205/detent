"""Test Click CLI commands."""

from __future__ import annotations

import logging
import pathlib
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner


@pytest.fixture(autouse=True)
def reset_root_log_level():
    """Reset root log level after each test."""
    original = logging.root.level
    yield
    logging.root.setLevel(original)


def test_cli_version():
    """detent --version should show version."""
    from detent.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "0.1.0" in result.output


def test_cli_help():
    """detent --help should show help."""
    from detent.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "init" in result.output
    assert "run" in result.output
    assert "status" in result.output
    assert "rollback" in result.output


def test_init_command_help():
    """detent init --help should show init help."""
    from detent.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["init", "--help"])

    assert result.exit_code == 0
    assert "Initialize Detent" in result.output


def test_run_command_help():
    """detent run --help should show run help."""
    from detent.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["run", "--help"])

    assert result.exit_code == 0
    assert "Verify a file" in result.output


def test_status_command_help():
    """detent status --help should show status help."""
    from detent.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["status", "--help"])

    assert result.exit_code == 0
    assert "session" in result.output.lower()


def test_rollback_command_help():
    """detent rollback --help should show rollback help."""
    from detent.cli import main

    runner = CliRunner()
    result = runner.invoke(main, ["rollback", "--help"])

    assert result.exit_code == 0
    assert "checkpoint" in result.output.lower()


def test_verbose_sets_debug_logging() -> None:
    """--verbose flag should set root logging level to DEBUG."""
    from detent.cli import main

    runner = CliRunner()
    runner.invoke(main, ["--verbose", "status"])
    assert logging.root.level == logging.DEBUG


def test_verbose_short_flag_sets_debug_logging() -> None:
    """-v short flag should set root logging level to DEBUG."""
    from detent.cli import main

    runner = CliRunner()
    runner.invoke(main, ["-v", "status"])
    assert logging.root.level == logging.DEBUG


def test_config_flag_accepted(tmp_path: pathlib.Path) -> None:
    """--config flag should be accepted without error on status command."""
    from detent.cli import main

    config_file = tmp_path / "detent.yaml"
    config_file.write_text("policy: strict\n")
    runner = CliRunner()
    result = runner.invoke(main, ["--config", str(config_file), "status"])
    assert result.exit_code == 0


def test_config_path_propagated_to_run(tmp_path: pathlib.Path) -> None:
    """--config flag should pass the path to DetentConfig.load() when run is invoked."""
    from detent.cli import main

    config_file = tmp_path / "detent.yaml"
    config_file.write_text("policy: standard\n")
    target_file = tmp_path / "main.py"
    target_file.write_text("x = 1\n")

    runner = CliRunner()
    with patch("detent.cli.app.DetentConfig") as mock_app_cfg, patch("detent.cli.run.DetentConfig") as mock_run_cfg:
        mock_app_cfg.load.return_value = MagicMock(
            policy="standard",
            pipeline=MagicMock(stages=[]),
            get_enabled_stages=lambda: [],
            telemetry=MagicMock(enabled=False),
        )
        runner.invoke(main, ["--config", str(config_file), "run", str(target_file)])
        mock_app_cfg.load.assert_called_once_with(path=str(config_file))
        mock_run_cfg.load.assert_not_called()


def test_no_config_flag_passes_none_to_run(tmp_path: pathlib.Path) -> None:
    """Without --config, DetentConfig.load() should be called with path=None."""
    from detent.cli import main

    target_file = tmp_path / "main.py"
    target_file.write_text("x = 1\n")

    runner = CliRunner()
    with patch("detent.cli.app.DetentConfig") as mock_app_cfg, patch("detent.cli.run.DetentConfig") as mock_run_cfg:
        mock_app_cfg.load.return_value = MagicMock(
            policy="standard",
            pipeline=MagicMock(stages=[]),
            get_enabled_stages=lambda: [],
            telemetry=MagicMock(enabled=False),
        )
        runner.invoke(main, ["run", str(target_file)])
        mock_app_cfg.load.assert_called_once_with(path=None)
        mock_run_cfg.load.assert_not_called()


def test_config_envvar_accepted(tmp_path: pathlib.Path) -> None:
    """DETENT_CONFIG env var should be accepted as --config source."""
    from detent.cli import main

    config_file = tmp_path / "detent.yaml"
    config_file.write_text("policy: permissive\n")
    runner = CliRunner()
    result = runner.invoke(main, ["status"], env={"DETENT_CONFIG": str(config_file)})
    assert result.exit_code == 0
