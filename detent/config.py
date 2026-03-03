"""Configuration loader for Detent.

Loads from detent.yaml or the path specified by DETENT_CONFIG env var.
Provides sensible defaults when no config file is found.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# ─── Default values ──────────────────────────────────────────────────────────

DEFAULT_PROXY_HOST = "127.0.0.1"
DEFAULT_PROXY_PORT = 7070
DEFAULT_IPC_TIMEOUT_MS = 4000
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_POLICY = "standard"
DEFAULT_CONFIG_FILENAME = "detent.yaml"


# ─── Pydantic models ─────────────────────────────────────────────────────────


class StageConfig(BaseModel):
    """Configuration for a single verification stage."""

    name: str = Field(description="Stage name (syntax, lint, typecheck, tests)")
    enabled: bool = Field(default=True, description="Whether this stage is active")
    timeout: int = Field(default=30, description="Timeout in seconds for this stage")
    tools: list[str] = Field(default_factory=list, description="Tool overrides for this stage")
    options: dict[str, Any] = Field(default_factory=dict, description="Stage-specific options")


class PipelineConfig(BaseModel):
    """Configuration for the verification pipeline."""

    parallel: bool = Field(default=False, description="Run independent stages in parallel")
    fail_fast: bool = Field(default=True, description="Halt on first P0 stage failure")
    stages: list[StageConfig] = Field(default_factory=list, description="Ordered list of stage configs")


class ProxyConfig(BaseModel):
    """Configuration for the HTTP reverse proxy."""

    host: str = Field(default=DEFAULT_PROXY_HOST, description="Bind address")
    port: int = Field(default=DEFAULT_PROXY_PORT, description="Listen port")


class DetentConfig(BaseModel):
    """Root configuration for Detent.

    Loaded from detent.yaml or the DETENT_CONFIG env var path.
    All fields have sensible defaults for zero-config startup.
    """

    policy: str = Field(default=DEFAULT_POLICY, description="Policy profile: strict | standard | permissive")
    agent: str = Field(default="auto", description="Agent type (auto-detected by detent init)")
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, description="Logging level")
    ipc_timeout_ms: int = Field(default=DEFAULT_IPC_TIMEOUT_MS, description="IPC control channel timeout (ms)")
    strict_mode: bool = Field(default=False, description="Fail-closed when proxy is unavailable")

    @classmethod
    def load(cls, path: str | Path | None = None) -> DetentConfig:
        """Load configuration from a YAML file.

        Resolution order:
        1. Explicit path argument
        2. DETENT_CONFIG environment variable
        3. detent.yaml in the current directory
        4. Default configuration (no file needed)

        Args:
            path: Optional explicit path to config file.

        Returns:
            Loaded DetentConfig instance.
        """
        config_path = cls._resolve_path(path)

        if config_path is not None and config_path.exists():
            logger.info(f"Loading config from {config_path}")
            return cls._from_yaml(config_path)

        if config_path is not None and not config_path.exists():
            logger.warning(f"Config file not found: {config_path}; using defaults")

        logger.info("No config file found; using default configuration")
        return cls._with_default_stages()

    @classmethod
    def _resolve_path(cls, path: str | Path | None) -> Path | None:
        """Resolve the config file path from argument, env var, or default."""
        if path is not None:
            return Path(path)

        env_path = os.environ.get("DETENT_CONFIG")
        if env_path:
            return Path(env_path)

        default_path = Path(DEFAULT_CONFIG_FILENAME)
        if default_path.exists():
            return default_path

        return None

    @classmethod
    def _from_yaml(cls, path: Path) -> DetentConfig:
        """Parse a YAML config file into a DetentConfig."""
        with open(path) as f:
            raw = yaml.safe_load(f)

        if raw is None:
            return cls._with_default_stages()

        # Normalize 'stages' key from top-level into pipeline config
        if "stages" in raw and "pipeline" not in raw:
            raw["pipeline"] = {"stages": raw.pop("stages")}
        elif "stages" in raw and "pipeline" in raw:
            raw["pipeline"]["stages"] = raw.pop("stages")

        return cls.model_validate(raw)

    @classmethod
    def _with_default_stages(cls) -> DetentConfig:
        """Create a config with the default v0.1 pipeline stages."""
        default_stages = [
            StageConfig(name="syntax", enabled=True),
            StageConfig(name="lint", enabled=True),
            StageConfig(name="typecheck", enabled=True, timeout=30),
            StageConfig(name="tests", enabled=True, timeout=60),
        ]
        return cls(pipeline=PipelineConfig(stages=default_stages))

    def get_enabled_stages(self) -> list[StageConfig]:
        """Return only enabled stages in pipeline order."""
        return [s for s in self.pipeline.stages if s.enabled]
