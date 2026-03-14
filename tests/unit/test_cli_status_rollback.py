"""Test detent status and rollback commands."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


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

    with patch("detent.cli.SessionManager") as mock_mgr_class:
        mock_mgr = MagicMock()
        mock_mgr.load_or_create.return_value = session
        mock_mgr_class.return_value = mock_mgr

        with patch("detent.cli.console"):
            # Just verify it doesn't crash
            show_status()


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

    with patch("detent.cli.SessionManager") as mock_mgr_class:
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
                await do_rollback("chk_before_write_000")
