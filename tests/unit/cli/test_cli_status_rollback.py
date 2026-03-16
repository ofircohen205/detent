"""Test detent status and rollback commands."""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import click
import pytest
from click.testing import CliRunner


def test_show_status(tmp_path):
    """show_status should display session and checkpoints."""
    from detent.cli import show_status

    # Create session
    session_dir = tmp_path / "session"
    session_dir.mkdir()
    session_file = session_dir / "default.json"

    session = {
        "session_id": "sess_test123",
        "started_at": "2026-03-08T14:00:00Z",
        "checkpoints": [
            {
                "ref": "chk_before_write_000",
                "file": "src/main.py",
                "created_at": "2026-03-08T14:00:01Z",
                "status": "created",
            },
            {
                "ref": "chk_before_write_001",
                "file": "src/utils.py",
                "created_at": "2026-03-08T14:00:02Z",
                "status": "rolled_back",
            },
        ],
    }

    session_file.write_text(json.dumps(session))

    with patch("detent.cli.status.SessionManager") as mock_mgr_class:
        mock_mgr = MagicMock()
        mock_mgr.load_or_create.return_value = session
        mock_mgr_class.return_value = mock_mgr

        with patch("detent.cli.console"):
            # Just verify it doesn't crash
            show_status()


def test_status_json_output(tmp_path):
    """status --json should output valid JSON with 'checkpoints' key."""
    from detent.cli import show_status

    session = {
        "session_id": "sess_abc",
        "checkpoints": [
            {
                "ref": "chk_000",
                "file": "x.py",
                "created_at": "2026-03-14T00:00:00Z",
                "status": "created",
            }
        ],
    }
    output_lines = []
    with (
        patch("detent.cli.status.SessionManager") as mock_cls,
        patch("detent.cli.status.click.echo") as mock_echo,
    ):
        mock_cls.return_value.load_or_create.return_value = session
        show_status(json_mode=True)
        for call in mock_echo.call_args_list:
            output_lines.append(call.args[0])

    combined = "\n".join(output_lines)
    parsed = json.loads(combined)
    assert "checkpoints" in parsed
    assert parsed["checkpoints"][0]["ref"] == "chk_000"


def test_status_reset_clears_session(tmp_path):
    """status --reset should delete the session file after confirmation."""
    from detent.cli import main

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        import os

        os.makedirs(".detent/session", exist_ok=True)
        with open(".detent/session/default.json", "w") as f:
            f.write('{"session_id": "s", "checkpoints": []}')
        result = runner.invoke(main, ["status", "--reset"], input="y\n")
    assert result.exit_code == 0
    assert "Session reset" in result.output


def test_status_reset_declined_keeps_session(tmp_path):
    """status --reset declined should keep session file."""
    from detent.cli import main

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        import os

        os.makedirs(".detent/session", exist_ok=True)
        with open(".detent/session/default.json", "w") as f:
            f.write('{"session_id": "s", "checkpoints": []}')
        result = runner.invoke(main, ["status", "--reset"], input="n\n")
    assert result.exit_code == 0


@pytest.mark.asyncio
async def test_do_rollback(tmp_path):
    """do_rollback should restore checkpoint."""
    from detent.cli import do_rollback

    session_dir = tmp_path / "session"
    session_dir.mkdir()
    session_file = session_dir / "default.json"

    session = {
        "session_id": "sess_test123",
        "checkpoints": [
            {
                "ref": "chk_before_write_000",
                "file": "src/main.py",
                "status": "created",
            }
        ],
    }

    session_file.write_text(json.dumps(session))

    with patch("detent.cli.rollback.SessionManager") as mock_mgr_class:
        mock_mgr = MagicMock()
        mock_mgr.load_or_create.return_value = session
        mock_mgr.get_checkpoint.return_value = session["checkpoints"][0]
        mock_mgr_class.return_value = mock_mgr

        with patch("detent.cli.rollback.CheckpointEngine") as mock_chk_class:
            mock_chk = MagicMock()
            mock_chk.rollback = AsyncMock()
            mock_chk_class.return_value = mock_chk

            with patch("detent.cli.console"):
                # Just verify it doesn't crash
                await do_rollback("chk_before_write_000", yes=True)


def test_rollback_latest_selects_most_recent(tmp_path):
    """rollback --latest should roll back the last checkpoint in the list."""
    from detent.cli import do_rollback

    session = {
        "session_id": "sess_test",
        "checkpoints": [
            {
                "ref": "chk_000",
                "file": "a.py",
                "created_at": "2026-03-14T00:00:00Z",
                "status": "created",
            },
            {
                "ref": "chk_001",
                "file": "b.py",
                "created_at": "2026-03-14T00:00:01Z",
                "status": "created",
            },
        ],
    }
    with (
        patch("detent.cli.rollback.SessionManager") as mock_cls,
        patch("detent.cli.rollback.CheckpointEngine") as mock_chk,
    ):
        mock_cls.return_value.load_or_create.return_value = session
        mock_cls.return_value.get_checkpoint.side_effect = lambda s, r: next(
            (c for c in s["checkpoints"] if c["ref"] == r), None
        )
        mock_chk.return_value.rollback = AsyncMock()

        asyncio.run(do_rollback(ref=None, latest=True, yes=True))

        mock_chk.return_value.rollback.assert_called_once_with("chk_001")


def test_rollback_latest_no_checkpoints_exits_1(tmp_path):
    """rollback --latest with no checkpoints should raise ClickException."""
    from detent.cli import do_rollback

    session = {"session_id": "sess_test", "checkpoints": []}
    with patch("detent.cli.rollback.SessionManager") as mock_cls:
        mock_cls.return_value.load_or_create.return_value = session
        with pytest.raises(click.ClickException, match="No checkpoints"):
            asyncio.run(do_rollback(ref=None, latest=True, yes=True))


def test_rollback_confirmation_required(tmp_path):
    """rollback without --yes should prompt for confirmation."""
    from detent.cli import main

    runner = CliRunner()
    with (
        patch("detent.cli.rollback.SessionManager") as mock_cls,
        patch("detent.cli.rollback.CheckpointEngine") as mock_chk,
    ):
        session = {
            "session_id": "s",
            "checkpoints": [
                {
                    "ref": "chk_000",
                    "file": "a.py",
                    "created_at": "2026-03-14T00:00:00Z",
                    "status": "created",
                }
            ],
        }
        mock_cls.return_value.load_or_create.return_value = session
        mock_cls.return_value.get_checkpoint.return_value = session["checkpoints"][0]
        mock_chk.return_value.rollback = AsyncMock()
        result = runner.invoke(main, ["rollback", "chk_000"], input="n\n")
    assert result.exit_code == 0
    assert "Aborted" in result.output
