"""Test detent init command."""

from pathlib import Path
from unittest.mock import patch

import yaml


def test_detect_agent_from_env():
    """detect_agent should find agent from env variables."""
    from detent.cli import detect_agent

    with patch.dict("os.environ", {"ANTHROPIC_BASE_URL": "http://localhost:7070"}):
        agent = detect_agent()
        assert agent == "claude-code"


def test_detect_agent_from_claude_config():
    """detect_agent should find Claude Code config."""
    from detent.cli import detect_agent

    with patch("pathlib.Path.exists", return_value=True):
        agent = detect_agent()
        # This will detect from mocked config
        assert agent in ["claude-code", "langgraph"]


def test_detect_agent_default():
    """detect_agent should default to unknown when nothing is found."""
    from detent.cli import detect_agent

    with (
        patch("pathlib.Path.exists", return_value=False),
        patch("pathlib.Path.read_text", return_value=""),
        patch.dict("os.environ", {}, clear=True),
        patch("pathlib.Path.home", return_value=Path("/tmp/fakehome_nonexistent")),
    ):
        agent = detect_agent()
        assert agent == "unknown"


def test_init_creates_session_dir(tmp_path):
    """init_interactive should create .detent/session/ directory."""
    from detent.cli import create_session_dir

    session_dir = tmp_path / ".detent" / "session"
    create_session_dir(session_dir)

    assert session_dir.exists()
    assert session_dir.is_dir()


def test_init_yaml_serialization(tmp_path):
    """detent.yaml should serialize and deserialize correctly."""
    from detent.config import DetentConfig, PipelineConfig, StageConfig

    # Create config
    config = DetentConfig(
        agent="claude-code",
        policy="standard",
        pipeline=PipelineConfig(
            parallel=False,
            fail_fast=True,
            stages=[
                StageConfig(name="syntax", enabled=True),
                StageConfig(name="lint", enabled=True),
            ],
        ),
    )

    # Serialize to YAML
    yaml_str = yaml.dump(config.model_dump())

    # Deserialize back
    loaded = yaml.safe_load(yaml_str)
    reconfig = DetentConfig.model_validate(loaded)

    # Verify round-trip
    assert reconfig.agent == "claude-code"
    assert reconfig.policy == "standard"
    assert len(reconfig.pipeline.stages) == 2


def test_detect_agent_cursor_project_dir(tmp_path, monkeypatch):
    """detect_agent should detect Cursor via .cursor/ in project root."""
    from detent.cli.utils import detect_agent

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".cursor").mkdir()
    with patch.dict("os.environ", {}, clear=True), patch("pathlib.Path.home", return_value=tmp_path / "fakehome"):
        agent = detect_agent()
    assert agent == "cursor"


def test_detect_agent_cursor_home_dir(tmp_path, monkeypatch):
    """detect_agent should detect Cursor via ~/.cursor/ in home dir."""
    from detent.cli.utils import detect_agent

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    monkeypatch.chdir(project_dir)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    (fake_home / ".cursor").mkdir()
    with patch.dict("os.environ", {}, clear=True), patch("pathlib.Path.home", return_value=fake_home):
        agent = detect_agent()
    assert agent == "cursor"


def test_detect_agent_prefers_claude_over_cursor(tmp_path, monkeypatch):
    """Claude Code detection takes priority over Cursor."""
    from detent.cli.utils import detect_agent

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude" / "settings.json").touch()
    (tmp_path / ".cursor").mkdir()
    with patch.dict("os.environ", {}, clear=True), patch("pathlib.Path.home", return_value=tmp_path / "fakehome"):
        agent = detect_agent()
    assert agent == "claude-code"


def test_init_non_interactive_writes_yaml(tmp_path):
    """init --non-interactive should write detent.yaml without prompts."""
    from click.testing import CliRunner

    from detent.cli import main

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["init", "--non-interactive"])
        assert result.exit_code == 0
        assert Path("detent.yaml").exists()
        config_data = yaml.safe_load(Path("detent.yaml").read_text())
        assert config_data["policy"] in ["strict", "standard", "permissive"]


def test_init_non_interactive_no_force_existing(tmp_path):
    """init --non-interactive should exit 1 if detent.yaml exists without --force."""
    from click.testing import CliRunner

    from detent.cli import main

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("detent.yaml").write_text("policy: strict\n")
        result = runner.invoke(main, ["init", "--non-interactive"])
    assert result.exit_code == 1


def test_init_non_interactive_force_overwrites(tmp_path):
    """init --non-interactive --force should overwrite existing detent.yaml."""
    from click.testing import CliRunner

    from detent.cli import main

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        Path("detent.yaml").write_text("policy: strict\n")
        result = runner.invoke(main, ["init", "--non-interactive", "--force"])
    assert result.exit_code == 0
