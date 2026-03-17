# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Detent Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Configuration loader for Detent."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Literal

import structlog
import yaml
from pydantic import BaseModel, Field

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

# ─── Default values ──────────────────────────────────────────────────────────

DEFAULT_PROXY_HOST = "127.0.0.1"
DEFAULT_PROXY_PORT = 7070

# ─── Upstream hosts ──────────────────────────────────────────────────────────

UPSTREAM_HOST_ANTHROPIC = "api.anthropic.com"
UPSTREAM_HOST_OPENAI = "api.openai.com"
ALLOWED_UPSTREAM_HOSTS: frozenset[str] = frozenset({UPSTREAM_HOST_ANTHROPIC, UPSTREAM_HOST_OPENAI})
DEFAULT_IPC_TIMEOUT_MS = 4000
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_POLICY = "standard"
DEFAULT_CONFIG_FILENAME = "detent.yaml"


class CircuitBreakerConfig(BaseModel):
    """Circuit breaker settings for individual pipeline stages."""

    enabled: bool = Field(
        default=False,
        description="Enable the stage-level circuit breaker",
    )
    failure_threshold: int = Field(
        default=5,
        description="Number of successive failures before the circuit opens",
    )
    recovery_window_s: float = Field(
        default=60.0,
        description="Seconds the breaker stays open before allowing a probe",
    )
    behavior: Literal["skip", "warn"] = Field(
        default="warn",
        description="Behavior when the circuit is open",
    )


class StageConfig(BaseModel):
    """Configuration for a single verification stage."""

    name: str = Field(description="Stage name (syntax, lint, typecheck, tests)")
    enabled: bool = Field(default=True, description="Whether this stage is active")
    timeout: int = Field(default=30, description="Timeout in seconds for this stage")
    tools: list[str] = Field(default_factory=list, description="Tool overrides for this stage")
    options: dict[str, Any] = Field(default_factory=dict, description="Stage-specific options")
    circuit_breaker: CircuitBreakerConfig = Field(
        default_factory=CircuitBreakerConfig,
        description="Circuit breaker settings for this stage",
    )


class PipelineConfig(BaseModel):
    """Configuration for the verification pipeline."""

    parallel: bool = Field(default=False, description="Run independent stages in parallel")
    fail_fast: bool = Field(default=True, description="Halt on first P0 stage failure")
    stages: list[StageConfig] = Field(default_factory=list, description="Ordered list of stage configs")


class ProxyConfig(BaseModel):
    """Configuration for the HTTP reverse proxy."""

    host: str = Field(default=DEFAULT_PROXY_HOST, description="Bind address")
    port: int = Field(default=DEFAULT_PROXY_PORT, description="Listen port")


class TelemetryConfig(BaseModel):
    """OpenTelemetry configuration."""

    enabled: bool = Field(
        default=True,
        description="Enable OpenTelemetry instrumentation",
    )
    exporter: Literal["console", "otlp", "none"] = Field(
        default="console",
        description="Exporter backend",
    )
    otlp_endpoint: str = Field(
        default="http://localhost:4317",
        description="OTLP collector endpoint",
    )
    service_name: str = Field(
        default="detent",
        description="Service name advertised by telemetry",
    )


class DetentConfig(BaseModel):
    """Root configuration for Detent."""

    policy: str = Field(default=DEFAULT_POLICY, description="Policy profile: strict | standard | permissive")
    agent: str = Field(default="auto", description="Agent type (auto-detected by detent init)")
    proxy: ProxyConfig = Field(default_factory=ProxyConfig)
    pipeline: PipelineConfig = Field(default_factory=PipelineConfig)
    log_level: str = Field(default=DEFAULT_LOG_LEVEL, description="Logging level")
    ipc_timeout_ms: int = Field(default=DEFAULT_IPC_TIMEOUT_MS, description="IPC control channel timeout (ms)")
    strict_mode: bool = Field(default=False, description="Fail-closed when proxy is unavailable")
    telemetry: TelemetryConfig = Field(
        default_factory=TelemetryConfig,
        description="OpenTelemetry configuration",
    )

    @classmethod
    def load(cls, path: str | Path | None = None) -> DetentConfig:
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
        with open(path) as f:
            raw = yaml.safe_load(f)
        if raw is None:
            return cls._with_default_stages()
        if "stages" in raw and "pipeline" not in raw:
            raw["pipeline"] = {"stages": raw.pop("stages")}
        elif "stages" in raw and "pipeline" in raw:
            raw["pipeline"]["stages"] = raw.pop("stages")
        return cls.model_validate(raw)

    @classmethod
    def _with_default_stages(cls) -> DetentConfig:
        default_stages = [
            StageConfig(name="syntax", enabled=True),
            StageConfig(name="lint", enabled=True),
            StageConfig(name="typecheck", enabled=True, timeout=30),
            StageConfig(name="tests", enabled=True, timeout=60),
            StageConfig(
                name="security",
                enabled=True,
                timeout=30,
                options={
                    "semgrep": {"enabled": True, "rulesets": ["p/python", "p/owasp-top-ten"]},
                    "bandit": {"enabled": True, "confidence": "low"},
                },
            ),
        ]
        return cls(pipeline=PipelineConfig(stages=default_stages))

    def get_enabled_stages(self) -> list[StageConfig]:
        return [s for s in self.pipeline.stages if s.enabled]
