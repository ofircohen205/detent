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


def test_hook_matcher_is_file_write_tools_only(project_dir):
    """Hook entry uses matcher targeting only file-writing tools."""
    configure_claude_code_hook(port=7070)

    data = json.loads((project_dir / ".claude" / "settings.json").read_text())
    matchers = [entry["matcher"] for entry in data["hooks"]["PreToolUse"]]
    assert any(m == "Write|Edit|NotebookEdit" for m in matchers)


@pytest.mark.parametrize("stale_matcher", ["", "*", "Write"])
def test_migrates_stale_matcher_to_canonical(project_dir, stale_matcher):
    """Re-running upgrades any stale Detent hook matcher to the canonical value."""
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    stale = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": stale_matcher,
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
    settings_path.write_text(json.dumps(stale))

    result = configure_claude_code_hook(port=7070)

    assert result is True
    data = json.loads(settings_path.read_text())
    pretool_entries = data["hooks"]["PreToolUse"]
    assert len(pretool_entries) == 1, "stale entry must be updated in-place, not duplicated"
    assert pretool_entries[0]["matcher"] == "Write|Edit|NotebookEdit"


def test_migrates_all_stale_entries_when_duplicates_exist(project_dir):
    """All stale Detent entries are removed and replaced with a single correct entry."""
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    cmd = "curl -s -X POST http://127.0.0.1:7070/hooks/claude-code -H 'Content-Type: application/json' -d @-"
    stale = {
        "hooks": {
            "PreToolUse": [
                {"matcher": "", "hooks": [{"type": "command", "command": cmd}]},
                {"matcher": "*", "hooks": [{"type": "command", "command": cmd}]},
            ]
        }
    }
    settings_path.write_text(json.dumps(stale))

    result = configure_claude_code_hook(port=7070)

    assert result is True
    data = json.loads(settings_path.read_text())
    detent_entries = [
        e
        for e in data["hooks"]["PreToolUse"]
        if any("/hooks/claude-code" in h.get("command", "") for h in e.get("hooks", []))
    ]
    assert len(detent_entries) == 1
    assert detent_entries[0]["matcher"] == "Write|Edit|NotebookEdit"


def test_skips_when_hook_already_correct(project_dir):
    """Does not duplicate or modify the entry when matcher is already correct."""
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    existing = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Write|Edit|NotebookEdit",
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

    result = configure_claude_code_hook(port=7070)

    assert result is True
    data = json.loads(settings_path.read_text())
    detent_entries = [e for e in data["hooks"]["PreToolUse"] if e["matcher"] == "Write|Edit|NotebookEdit"]
    assert len(detent_entries) == 1  # no duplication


def test_adds_hooks_key_when_settings_exists_without_hooks(project_dir):
    """Works correctly when settings.json exists but has no 'hooks' key."""
    settings_path = project_dir / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(json.dumps({"theme": "dark", "language": "en"}))

    result = configure_claude_code_hook(port=7070)

    assert result is True
    data = json.loads(settings_path.read_text())
    assert data["theme"] == "dark"  # existing keys preserved
    assert "PreToolUse" in data["hooks"]


def test_returns_false_on_write_oserror(project_dir, monkeypatch):
    """Returns False when writing settings.json raises OSError."""
    from unittest.mock import patch

    with patch("pathlib.Path.write_text", side_effect=OSError("read-only filesystem")):
        result = configure_claude_code_hook(port=7070)
    assert result is False


def test_raises_on_invalid_port(project_dir):
    """configure_claude_code_hook raises ValueError for out-of-range port."""
    with pytest.raises(ValueError, match="port must be 1-65535"):
        configure_claude_code_hook(port=0)
    with pytest.raises(ValueError, match="port must be 1-65535"):
        configure_claude_code_hook(port=99999)
    with pytest.raises((ValueError, TypeError)):
        configure_claude_code_hook(port="7070")  # type: ignore[arg-type]


def test_returns_false_when_dot_claude_is_symlink_escaping_project(project_dir, tmp_path_factory):
    """Returns False when .claude/ is a symlink pointing outside the project root."""
    outside = tmp_path_factory.mktemp("outside") / "outside_dir"
    outside.mkdir()
    dot_claude = project_dir / ".claude"
    dot_claude.symlink_to(outside)

    result = configure_claude_code_hook(port=7070)

    assert result is False
