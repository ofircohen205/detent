"""Tests for VerificationPipeline orchestration."""

from __future__ import annotations

import logging

import pytest

from detent.config import DetentConfig, PipelineConfig, StageConfig
from detent.pipeline.pipeline import VerificationPipeline, _detect_language
from detent.pipeline.result import Finding, VerificationResult
from detent.schema import AgentAction
from detent.stages.base import VerificationStage
from tests.conftest import make_action

# ─── Mock stage helpers ───────────────────────────────────────────────────────


class MockStage(VerificationStage):
    """A stage that records calls and returns configured findings."""

    def __init__(
        self,
        stage_name: str,
        findings: list[Finding] | None = None,
        supported_lang: str | None = None,
    ) -> None:
        self._stage_name = stage_name
        self._findings = findings or []
        self._supported_lang = supported_lang  # None = all languages
        self.call_count = 0

    @property
    def name(self) -> str:
        return self._stage_name

    def supports_language(self, lang: str) -> bool:
        if self._supported_lang is None:
            return True
        return lang == self._supported_lang

    async def _run(self, action: AgentAction) -> VerificationResult:
        self.call_count += 1
        return VerificationResult(
            stage=self._stage_name,
            passed=not any(f.severity == "error" for f in self._findings),
            findings=self._findings,
            duration_ms=1.0,
        )


class OrderTrackingMock(MockStage):
    """A mock stage that records the order in which stages are called."""

    def __init__(self, stage_name: str, call_order: list[str]) -> None:
        super().__init__(stage_name)
        self._call_order = call_order

    async def _run(self, action: AgentAction) -> VerificationResult:
        self._call_order.append(self.name)
        return await super()._run(action)


def make_error_finding(stage: str = "mock") -> Finding:
    return Finding(severity="error", file="/src/main.py", message="error", stage=stage)


def make_warning_finding(stage: str = "mock") -> Finding:
    return Finding(severity="warning", file="/src/main.py", message="warning", stage=stage)


def make_pipeline_config(*, parallel: bool = False, fail_fast: bool = True) -> PipelineConfig:
    return PipelineConfig(parallel=parallel, fail_fast=fail_fast)


# ─── _detect_language ─────────────────────────────────────────────────────────


def test_detect_language_python():
    assert _detect_language("/src/main.py") == "python"


def test_detect_language_typescript():
    assert _detect_language("/src/app.ts") == "typescript"


def test_detect_language_tsx():
    assert _detect_language("/src/app.tsx") == "typescript"


def test_detect_language_javascript():
    assert _detect_language("/src/app.js") == "javascript"


def test_detect_language_unknown_extension():
    assert _detect_language("/src/main.xyz") == "unknown"


def test_detect_language_no_extension():
    assert _detect_language("/src/Makefile") == "unknown"


# ─── Empty pipeline ───────────────────────────────────────────────────────────


async def test_empty_pipeline_passes():
    pipeline = VerificationPipeline(stages=[], config=make_pipeline_config())
    result = await pipeline.run(make_action())
    assert result.passed
    assert result.findings == []
    assert result.stage == "pipeline"


# ─── Sequential execution ─────────────────────────────────────────────────────


async def test_sequential_order():
    call_order: list[str] = []
    s1 = OrderTrackingMock("first", call_order)
    s2 = OrderTrackingMock("second", call_order)
    s3 = OrderTrackingMock("third", call_order)
    pipeline = VerificationPipeline(stages=[s1, s2, s3], config=make_pipeline_config())
    await pipeline.run(make_action())
    assert call_order == ["first", "second", "third"]


async def test_sequential_all_pass_aggregates_findings():
    s1 = MockStage("syntax")
    s2 = MockStage("lint", findings=[make_warning_finding("lint")])
    pipeline = VerificationPipeline(stages=[s1, s2], config=make_pipeline_config())
    result = await pipeline.run(make_action())
    assert result.passed
    assert len(result.findings) == 1
    assert result.findings[0].stage == "lint"


async def test_sequential_result_stage_is_pipeline():
    pipeline = VerificationPipeline(stages=[MockStage("syntax")], config=make_pipeline_config())
    result = await pipeline.run(make_action())
    assert result.stage == "pipeline"


async def test_sequential_result_duration_ms_positive():
    pipeline = VerificationPipeline(stages=[MockStage("syntax")], config=make_pipeline_config())
    result = await pipeline.run(make_action())
    assert result.duration_ms > 0


async def test_sequential_metadata_contains_stage_results():
    s1 = MockStage("syntax")
    s2 = MockStage("lint")
    pipeline = VerificationPipeline(stages=[s1, s2], config=make_pipeline_config())
    result = await pipeline.run(make_action())
    assert "stage_results" in result.metadata
    stages_data = result.metadata["stage_results"]
    assert len(stages_data) == 2
    assert stages_data[0]["stage"] == "syntax"
    assert stages_data[1]["stage"] == "lint"


# ─── Fail-fast ────────────────────────────────────────────────────────────────


async def test_fail_fast_halts_after_first_error_stage():
    s1 = MockStage("syntax", findings=[make_error_finding("syntax")])
    s2 = MockStage("lint")
    pipeline = VerificationPipeline(stages=[s1, s2], config=make_pipeline_config(fail_fast=True))
    result = await pipeline.run(make_action())
    assert not result.passed
    assert s1.call_count == 1
    assert s2.call_count == 0
    assert len(result.metadata["stage_results"]) == 1


async def test_fail_fast_warning_does_not_halt():
    s1 = MockStage("syntax", findings=[make_warning_finding("syntax")])
    s2 = MockStage("lint")
    pipeline = VerificationPipeline(stages=[s1, s2], config=make_pipeline_config(fail_fast=True))
    result = await pipeline.run(make_action())
    assert result.passed
    assert s2.call_count == 1


async def test_no_fail_fast_runs_all_stages():
    s1 = MockStage("syntax", findings=[make_error_finding("syntax")])
    s2 = MockStage("lint", findings=[make_error_finding("lint")])
    pipeline = VerificationPipeline(stages=[s1, s2], config=make_pipeline_config(fail_fast=False))
    result = await pipeline.run(make_action())
    assert not result.passed
    assert s1.call_count == 1
    assert s2.call_count == 1
    assert len(result.findings) == 2


async def test_pipeline_continues_after_stage_exception():
    class RaisingMock(MockStage):
        async def _run(self, action: AgentAction) -> VerificationResult:
            raise RuntimeError("boom")

    s1 = RaisingMock("syntax")
    s2 = MockStage("lint")
    pipeline = VerificationPipeline(stages=[s1, s2], config=make_pipeline_config(fail_fast=False))
    result = await pipeline.run(make_action())
    assert not result.passed  # exception → error finding → fails
    assert s2.call_count == 1  # pipeline continued despite s1 crash


# ─── Parallel mode ────────────────────────────────────────────────────────────


async def test_parallel_mode_runs_all_stages():
    s1 = MockStage("syntax")
    s2 = MockStage("lint")
    s3 = MockStage("typecheck")
    pipeline = VerificationPipeline(stages=[s1, s2, s3], config=make_pipeline_config(parallel=True))
    result = await pipeline.run(make_action())
    assert result.passed
    assert s1.call_count == 1
    assert s2.call_count == 1
    assert s3.call_count == 1


async def test_parallel_all_pass_aggregates_findings():
    s1 = MockStage("syntax", findings=[make_warning_finding("syntax")])
    s2 = MockStage("lint", findings=[make_warning_finding("lint")])
    pipeline = VerificationPipeline(stages=[s1, s2], config=make_pipeline_config(parallel=True, fail_fast=False))
    result = await pipeline.run(make_action())
    assert result.passed
    assert len(result.findings) == 2


async def test_parallel_fail_fast_truncates_at_first_error():
    s1 = MockStage("syntax")  # passes
    s2 = MockStage("lint", findings=[make_error_finding("lint")])  # errors
    s3 = MockStage("typecheck")  # would pass, but truncated
    pipeline = VerificationPipeline(
        stages=[s1, s2, s3],
        config=make_pipeline_config(parallel=True, fail_fast=True),
    )
    result = await pipeline.run(make_action())
    assert not result.passed
    # s1 passes, s2 errors → metadata truncated at s2 (2 entries, not 1 or 3)
    assert len(result.metadata["stage_results"]) == 2


# ─── Language filtering ───────────────────────────────────────────────────────


async def test_language_filtering_skips_unsupported_stage():
    py_only = MockStage("syntax", supported_lang="python")
    ts_only = MockStage("lint", supported_lang="typescript")
    pipeline = VerificationPipeline(stages=[py_only, ts_only], config=make_pipeline_config())
    result = await pipeline.run(make_action(file_path="/src/main.py"))
    assert result.passed
    assert py_only.call_count == 1
    assert ts_only.call_count == 0


async def test_language_filtering_all_filtered_passes():
    ts_only = MockStage("lint", supported_lang="typescript")
    pipeline = VerificationPipeline(stages=[ts_only], config=make_pipeline_config())
    result = await pipeline.run(make_action(file_path="/src/main.py"))
    assert result.passed
    assert ts_only.call_count == 0


async def test_language_filtering_unknown_extension_runs_all_stages():
    universal = MockStage("syntax")  # supports_language returns True for all
    pipeline = VerificationPipeline(stages=[universal], config=make_pipeline_config())
    result = await pipeline.run(make_action(file_path="/src/main.xyz"))
    assert result.passed
    assert universal.call_count == 1


async def test_language_specific_stage_skipped_for_unknown_extension():
    py_only = MockStage("syntax", supported_lang="python")
    pipeline = VerificationPipeline(stages=[py_only], config=make_pipeline_config())
    result = await pipeline.run(make_action(file_path="/src/Makefile"))
    assert result.passed
    assert py_only.call_count == 0


# ─── from_config factory ──────────────────────────────────────────────────────


def test_from_config_builds_default_pipeline():
    config = DetentConfig._with_default_stages()
    pipeline = VerificationPipeline.from_config(config)
    stage_names = [s.name for s in pipeline._stages]
    assert stage_names == ["syntax", "lint", "typecheck", "tests"]


def test_from_config_skips_disabled_stages():
    config = DetentConfig(
        pipeline=PipelineConfig(
            stages=[
                StageConfig(name="syntax", enabled=True),
                StageConfig(name="lint", enabled=False),
            ]
        )
    )
    pipeline = VerificationPipeline.from_config(config)
    assert len(pipeline._stages) == 1
    assert pipeline._stages[0].name == "syntax"


def test_from_config_skips_unknown_stages_with_warning(caplog: pytest.LogCaptureFixture):
    config = DetentConfig(
        pipeline=PipelineConfig(
            stages=[
                StageConfig(name="syntax", enabled=True),
                StageConfig(name="nonexistent_stage", enabled=True),
            ]
        )
    )
    with caplog.at_level(logging.WARNING):
        pipeline = VerificationPipeline.from_config(config)
    assert len(pipeline._stages) == 1
    assert "nonexistent_stage" in caplog.text


def test_from_config_empty_stages_produces_empty_pipeline():
    config = DetentConfig(pipeline=PipelineConfig(stages=[]))
    pipeline = VerificationPipeline.from_config(config)
    assert pipeline._stages == []
