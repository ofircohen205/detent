"""Shared fixtures for Detent benchmark suite."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from detent.checkpoint.engine import CheckpointEngine
from detent.config import PipelineConfig, StageConfig
from detent.pipeline.pipeline import VerificationPipeline
from detent.pipeline.result import VerificationResult
from detent.schema import ActionType, AgentAction, RiskLevel
from detent.stages.base import VerificationStage


class _NoOpStage(VerificationStage):
    """Minimal stage that returns immediately with no findings."""

    @property
    def name(self) -> str:
        return "noop"

    async def _run(self, action: AgentAction) -> VerificationResult:
        return VerificationResult(stage=self.name, passed=True, findings=[], duration_ms=0.0)


def _make_pipeline(n_stages: int, *, parallel: bool = False) -> VerificationPipeline:
    """Build a pipeline with n_stages no-op stages."""
    cfg = PipelineConfig(parallel=parallel, fail_fast=False, stages=[])
    stages = [_NoOpStage(StageConfig(name="noop")) for _ in range(n_stages)]
    return VerificationPipeline(stages=stages, config=cfg)


def _make_action(file_path: str) -> AgentAction:
    """Build a minimal AgentAction for benchmarking."""
    return AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": file_path, "content": "x = 1\n"},
        tool_call_id="toolu_bench_001",
        session_id="sess_bench",
        checkpoint_ref="chk_bench_001",
        risk_level=RiskLevel.LOW,
    )


@pytest.fixture()
def py_action() -> AgentAction:
    """AgentAction targeting a Python file (no real file needed for mock stages)."""
    return _make_action("/tmp/bench_target.py")


@pytest.fixture()
def pipeline_no_stages() -> VerificationPipeline:
    """Pipeline with zero stages — measures pure framework overhead."""
    return _make_pipeline(0)


@pytest.fixture()
def pipeline_one_stage() -> VerificationPipeline:
    """Pipeline with one no-op stage — sequential."""
    return _make_pipeline(1)


@pytest.fixture()
def pipeline_five_stages_parallel() -> VerificationPipeline:
    """Pipeline with five no-op stages in parallel mode."""
    return _make_pipeline(5, parallel=True)


@pytest.fixture()
def checkpoint_engine() -> CheckpointEngine:
    """In-memory CheckpointEngine (no shadow git)."""
    return CheckpointEngine()


@pytest.fixture()
def tmp_1kb(tmp_path: Path) -> Path:
    """A 1 KB temporary Python file."""
    f = tmp_path / "file_1kb.py"
    f.write_bytes(b"x = 1\n" * 171)  # ~1 KB
    return f


@pytest.fixture()
def tmp_100kb(tmp_path: Path) -> Path:
    """A 100 KB temporary Python file."""
    f = tmp_path / "file_100kb.py"
    f.write_bytes(b"x = 1\n" * 17_000)  # ~100 KB
    return f
