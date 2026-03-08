"""Test Click CLI commands."""

from click.testing import CliRunner


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
