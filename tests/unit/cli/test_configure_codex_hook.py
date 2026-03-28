"""Tests for configure_codex_hook() in detent.cli.utils."""

import json
from unittest.mock import patch

import pytest

from detent.cli.utils import configure_codex_hook


@pytest.fixture()
def project_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_creates_hooks_json_when_missing(project_dir):
    """Creates .codex/hooks.json with PreToolUse Bash hook."""
    result = configure_codex_hook(port=7070)

    assert result is True
    hooks_path = project_dir / ".codex" / "hooks.json"
    assert hooks_path.exists()
    data = json.loads(hooks_path.read_text())
    commands = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert any("/hooks/codex" in cmd for cmd in commands)


def test_hooks_json_matcher_is_bash(project_dir):
    """Hook entry matcher is 'Bash' — only hookable tool in Codex today."""
    configure_codex_hook(port=7070)

    data = json.loads((project_dir / ".codex" / "hooks.json").read_text())
    matchers = [entry["matcher"] for entry in data["hooks"]["PreToolUse"]]
    assert any(m == "Bash" for m in matchers)


def test_does_not_write_instructions_md(project_dir):
    """Does not write to .codex/instructions.md — that was the old broken behavior."""
    configure_codex_hook(port=7070)
    assert not (project_dir / ".codex" / "instructions.md").exists()


def test_uses_configured_port(project_dir):
    """Hook command contains the specified port."""
    configure_codex_hook(port=8181)

    data = json.loads((project_dir / ".codex" / "hooks.json").read_text())
    commands = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert any("8181" in cmd for cmd in commands)


def test_raises_on_invalid_port(project_dir):
    """configure_codex_hook raises ValueError for out-of-range port."""
    with pytest.raises(ValueError, match="port must be 1-65535"):
        configure_codex_hook(port=0)


def test_idempotent_same_port_does_not_duplicate(project_dir):
    """Calling configure_codex_hook twice with the same port does not duplicate."""
    configure_codex_hook(port=7070)
    configure_codex_hook(port=7070)

    data = json.loads((project_dir / ".codex" / "hooks.json").read_text())
    detent_hooks = [
        h for e in data["hooks"]["PreToolUse"] for h in e["hooks"] if "/hooks/codex" in h.get("command", "")
    ]
    assert len(detent_hooks) == 1


def test_idempotent_different_port_does_not_duplicate(project_dir):
    """Re-running with a different port does not duplicate — first registration is preserved."""
    configure_codex_hook(port=7070)
    configure_codex_hook(port=8080)

    data = json.loads((project_dir / ".codex" / "hooks.json").read_text())
    detent_hooks = [
        h for e in data["hooks"]["PreToolUse"] for h in e["hooks"] if "/hooks/codex" in h.get("command", "")
    ]
    assert len(detent_hooks) == 1


def test_merges_with_existing_hooks(project_dir):
    """Preserves existing hooks already in hooks.json."""
    hooks_path = project_dir / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text(
        json.dumps(
            {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"type": "command", "command": "echo existing"}]}]}}
        )
    )

    configure_codex_hook(port=7070)

    data = json.loads(hooks_path.read_text())
    all_commands = [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]
    assert "echo existing" in all_commands
    assert any("/hooks/codex" in cmd for cmd in all_commands)


def test_returns_false_on_corrupt_hooks_file(project_dir):
    """Returns False when hooks.json is malformed JSON."""
    hooks_path = project_dir / ".codex" / "hooks.json"
    hooks_path.parent.mkdir(parents=True)
    hooks_path.write_text("{not valid json")

    assert configure_codex_hook(port=7070) is False


def test_returns_false_on_write_oserror(project_dir):
    """Returns False when writing hooks.json raises OSError."""
    with patch("pathlib.Path.write_text", side_effect=OSError("read-only filesystem")):
        result = configure_codex_hook(port=7070)
    assert result is False


def test_returns_false_when_dot_codex_is_symlink_escaping_project(project_dir, tmp_path_factory):
    """Returns False when .codex/ is a symlink pointing outside the project root."""
    outside = tmp_path_factory.mktemp("outside")
    (project_dir / ".codex").symlink_to(outside)

    assert configure_codex_hook(port=7070) is False
