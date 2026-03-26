"""Tests for configure_claude_code_hook() in detent.cli.utils."""

import json

import pytest

from detent.cli.utils import configure_claude_code_hook


@pytest.fixture()
def project_dir(tmp_path, monkeypatch):
    """Run each test inside a temporary project directory."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_creates_settings_file_when_missing(project_dir):
    """Creates .claude/settings.json with PreToolUse hook when file does not exist."""
    result = configure_claude_code_hook(port=7070)

    assert result is True
    settings_path = project_dir / ".claude" / "settings.json"
    assert settings_path.exists()

    data = json.loads(settings_path.read_text())
    hooks = data["hooks"]["PreToolUse"]
    commands = [h["command"] for entry in hooks for h in entry["hooks"]]
    assert any("/hooks/claude-code" in cmd for cmd in commands)


def test_uses_configured_port(project_dir):
    """Hook command contains the specified port."""
    configure_claude_code_hook(port=8080)

    data = json.loads((project_dir / ".claude" / "settings.json").read_text())
    hooks = data["hooks"]["PreToolUse"]
    commands = [h["command"] for entry in hooks for h in entry["hooks"]]
    assert any("8080" in cmd for cmd in commands)


def test_idempotent_does_not_duplicate_hook(project_dir):
    """Calling configure_claude_code_hook twice does not add duplicate entries."""
    configure_claude_code_hook(port=7070)
    configure_claude_code_hook(port=7070)

    data = json.loads((project_dir / ".claude" / "settings.json").read_text())
    hooks = data["hooks"]["PreToolUse"]
    detent_entries = [h for entry in hooks for h in entry["hooks"] if "/hooks/claude-code" in h.get("command", "")]
    assert len(detent_entries) == 1


def test_merges_with_existing_hooks(project_dir):
    """Preserves existing hooks already in settings.json."""
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    existing = {
        "hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo before"}]}]}
    }
    settings_path.write_text(json.dumps(existing))

    configure_claude_code_hook(port=7070)

    data = json.loads(settings_path.read_text())
    entries = data["hooks"]["PreToolUse"]
    # Both the existing entry and the new Detent entry should be present
    all_commands = [h["command"] for entry in entries for h in entry["hooks"]]
    assert "echo before" in all_commands
    assert any("/hooks/claude-code" in cmd for cmd in all_commands)


def test_returns_false_on_corrupt_settings_file(project_dir):
    """Returns False and does not crash when settings.json is malformed JSON."""
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text("{not valid json")

    result = configure_claude_code_hook(port=7070)

    assert result is False


def test_skips_when_hook_already_present_in_existing_entry(project_dir):
    """Does not add hook when a Detent hook command already exists."""
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    existing = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "curl -s -X POST http://127.0.0.1:7070/hooks/claude-code -H 'Content-Type: application/json' -d @-",
                        }
                    ],
                }
            ]
        }
    }
    settings_path.write_text(json.dumps(existing))
    original_mtime = settings_path.stat().st_mtime

    result = configure_claude_code_hook(port=7070)

    assert result is True
    # File should not be rewritten
    assert settings_path.stat().st_mtime == original_mtime
