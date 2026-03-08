"""Test detent init command."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
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
    """detect_agent should default to claude-code."""
    from detent.cli import detect_agent

    with patch("pathlib.Path.exists", return_value=False):
        with patch.dict("os.environ", {}, clear=True):
            agent = detect_agent()
            assert agent == "claude-code"


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
