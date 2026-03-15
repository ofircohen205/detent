"""Unit tests for detent.config — DetentConfig and YAML loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from detent.config import DetentConfig, PipelineConfig, ProxyConfig, StageConfig


class TestStageConfig:
    """Tests for StageConfig model."""

    def test_defaults(self) -> None:
        """Test stage config defaults."""
        stage = StageConfig(name="syntax")
        assert stage.enabled is True
        assert stage.timeout == 30
        assert stage.tools == []
        assert stage.options == {}

    def test_custom_values(self) -> None:
        """Test stage config with custom values."""
        stage = StageConfig(name="tests", enabled=False, timeout=120, tools=["pytest"])
        assert stage.name == "tests"
        assert stage.enabled is False
        assert stage.timeout == 120
        assert stage.tools == ["pytest"]


class TestProxyConfig:
    """Tests for ProxyConfig model."""

    def test_defaults(self) -> None:
        """Test proxy config defaults."""
        proxy = ProxyConfig()
        assert proxy.host == "127.0.0.1"
        assert proxy.port == 7070


class TestDetentConfig:
    """Tests for DetentConfig model."""

    def test_defaults(self) -> None:
        """Test config defaults."""
        config = DetentConfig()
        assert config.policy == "standard"
        assert config.agent == "auto"
        assert config.log_level == "INFO"
        assert config.strict_mode is False
        assert config.ipc_timeout_ms == 4000

    def test_default_stages(self) -> None:
        """Test _with_default_stages creates the standard v0.1 stages."""
        config = DetentConfig._with_default_stages()
        stages = config.get_enabled_stages()
        assert len(stages) == 5
        assert [s.name for s in stages] == ["syntax", "lint", "typecheck", "tests", "security"]

    def test_get_enabled_stages_filters(self) -> None:
        """Test get_enabled_stages filters out disabled stages."""
        config = DetentConfig(
            pipeline=PipelineConfig(
                stages=[
                    StageConfig(name="syntax", enabled=True),
                    StageConfig(name="lint", enabled=False),
                    StageConfig(name="typecheck", enabled=True),
                ]
            )
        )
        enabled = config.get_enabled_stages()
        assert len(enabled) == 2
        assert [s.name for s in enabled] == ["syntax", "typecheck"]

    def test_load_from_yaml(self, tmp_path: Path) -> None:
        """Test loading config from a YAML file."""
        config_file = tmp_path / "detent.yaml"
        config_file.write_text(
            """
policy: strict
proxy:
  port: 8080
stages:
  - name: syntax
    enabled: true
  - name: lint
    enabled: false
"""
        )
        config = DetentConfig.load(config_file)
        assert config.policy == "strict"
        assert config.proxy.port == 8080
        assert len(config.pipeline.stages) == 2
        assert config.pipeline.stages[0].name == "syntax"
        assert config.pipeline.stages[1].enabled is False

    def test_load_missing_file_uses_defaults(self, tmp_path: Path) -> None:
        """Test loading from non-existent file falls back to defaults."""
        config = DetentConfig.load(tmp_path / "nonexistent.yaml")
        assert config.policy == "standard"
        stages = config.get_enabled_stages()
        assert len(stages) == 5

    def test_load_empty_yaml(self, tmp_path: Path) -> None:
        """Test loading an empty YAML file falls back to defaults."""
        config_file = tmp_path / "detent.yaml"
        config_file.write_text("")
        config = DetentConfig.load(config_file)
        assert config.policy == "standard"
        stages = config.get_enabled_stages()
        assert len(stages) == 5

    def test_load_from_env_var(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test loading config from DETENT_CONFIG env var."""
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("policy: permissive\n")
        monkeypatch.setenv("DETENT_CONFIG", str(config_file))
        config = DetentConfig.load()
        assert config.policy == "permissive"

    def test_load_explicit_path_overrides_env(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test explicit path takes priority over env var."""
        env_file = tmp_path / "env.yaml"
        env_file.write_text("policy: permissive\n")
        explicit_file = tmp_path / "explicit.yaml"
        explicit_file.write_text("policy: strict\n")
        monkeypatch.setenv("DETENT_CONFIG", str(env_file))
        config = DetentConfig.load(explicit_file)
        assert config.policy == "strict"

    def test_stages_in_pipeline_section(self, tmp_path: Path) -> None:
        """Test stages nested under pipeline section."""
        config_file = tmp_path / "detent.yaml"
        config_file.write_text(
            """
pipeline:
  parallel: true
  fail_fast: false
  stages:
    - name: syntax
      enabled: true
"""
        )
        config = DetentConfig.load(config_file)
        assert config.pipeline.parallel is True
        assert config.pipeline.fail_fast is False
        assert len(config.pipeline.stages) == 1
