"""Test CLI session manager."""

import json
from pathlib import Path

import pytest


@pytest.fixture
def session_dir(tmp_path):
    """Create temporary session directory."""
    return tmp_path / "session"


def test_create_new_session(session_dir):
    """SessionManager should create new session when none exists."""
    from detent.cli import SessionManager

    mgr = SessionManager(session_dir)
    session = mgr.load_or_create()

    assert session["session_id"].startswith("sess_")
    assert session["active"] is True
    assert "started_at" in session
    assert session["checkpoints"] == []


def test_load_existing_session(session_dir):
    """SessionManager should load existing session."""
    from detent.cli import SessionManager

    # Create initial session
    session_dir.mkdir(parents=True)
    session_file = session_dir / "default.json"
    existing = {
        "session_id": "sess_test123",
        "active": True,
        "started_at": "2026-03-08T00:00:00Z",
        "checkpoints": [
            {
                "ref": "chk_before_write_000",
                "file": "src/main.py",
                "created_at": "2026-03-08T00:00:01Z",
                "status": "created",
            }
        ],
    }
    session_file.write_text(json.dumps(existing))

    # Load via SessionManager
    mgr = SessionManager(session_dir)
    session = mgr.load_or_create()

    assert session["session_id"] == "sess_test123"
    assert len(session["checkpoints"]) == 1


def test_save_session(session_dir):
    """SessionManager should persist session to disk."""
    from detent.cli import SessionManager

    mgr = SessionManager(session_dir)
    session = mgr.load_or_create()

    # Add checkpoint
    mgr.add_checkpoint(session, "chk_before_write_000", "src/main.py", "created")
    mgr.save(session)

    # Verify persisted
    session_file = session_dir / "default.json"
    assert session_file.exists()

    loaded = json.loads(session_file.read_text())
    assert loaded["session_id"] == session["session_id"]
    assert len(loaded["checkpoints"]) == 1


def test_add_checkpoint(session_dir):
    """SessionManager should track checkpoints."""
    from detent.cli import SessionManager

    mgr = SessionManager(session_dir)
    session = mgr.load_or_create()

    mgr.add_checkpoint(session, "chk_before_write_000", "src/main.py", "created")

    assert len(session["checkpoints"]) == 1
    assert session["checkpoints"][0]["ref"] == "chk_before_write_000"
    assert session["checkpoints"][0]["file"] == "src/main.py"


def test_get_checkpoint(session_dir):
    """SessionManager should retrieve checkpoints by ref."""
    from detent.cli import SessionManager

    mgr = SessionManager(session_dir)
    session = mgr.load_or_create()
    mgr.add_checkpoint(session, "chk_before_write_000", "src/main.py", "created")

    chk = mgr.get_checkpoint(session, "chk_before_write_000")
    assert chk is not None
    assert chk["file"] == "src/main.py"

    # Non-existent checkpoint
    chk = mgr.get_checkpoint(session, "chk_nonexistent")
    assert chk is None


def test_update_checkpoint_status(session_dir):
    """SessionManager should update checkpoint status."""
    from detent.cli import SessionManager

    mgr = SessionManager(session_dir)
    session = mgr.load_or_create()
    mgr.add_checkpoint(session, "chk_before_write_000", "src/main.py", "created")

    mgr.update_checkpoint_status(session, "chk_before_write_000", "rolled_back")

    chk = mgr.get_checkpoint(session, "chk_before_write_000")
    assert chk["status"] == "rolled_back"


def test_corrupted_session_creates_new(session_dir):
    """SessionManager should create new session if JSON is corrupted."""
    from detent.cli import SessionManager

    # Create corrupted session file
    session_dir.mkdir(parents=True)
    session_file = session_dir / "default.json"
    session_file.write_text("{invalid json}")

    mgr = SessionManager(session_dir)
    session = mgr.load_or_create()

    # Should create new session
    assert session["session_id"].startswith("sess_")
    assert session["active"] is True
