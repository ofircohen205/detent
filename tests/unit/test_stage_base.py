"""Tests for VerificationStage base class."""

from __future__ import annotations

from detent.pipeline.result import VerificationResult
from detent.schema import AgentAction
from detent.stages.base import VerificationStage
from tests.conftest import make_action


class AlwaysPassStage(VerificationStage):
    name = "always_pass"

    async def _run(self, action: AgentAction) -> VerificationResult:
        return VerificationResult(stage=self.name, passed=True, findings=[], duration_ms=0.1)


class AlwaysFailStage(VerificationStage):
    name = "always_fail"

    async def _run(self, action: AgentAction) -> VerificationResult:
        return VerificationResult(stage=self.name, passed=False, findings=[], duration_ms=0.1)


class ExplodingStage(VerificationStage):
    name = "exploding"

    async def _run(self, action: AgentAction) -> VerificationResult:
        raise RuntimeError("catastrophic failure")


async def test_passing_stage_returns_passed() -> None:
    result = await AlwaysPassStage().run(make_action())
    assert result.passed
    assert result.stage == "always_pass"


async def test_failing_stage_returns_failed() -> None:
    result = await AlwaysFailStage().run(make_action())
    assert not result.passed


async def test_exception_is_caught_and_returned_as_finding() -> None:
    result = await ExplodingStage().run(make_action())
    assert not result.passed
    assert len(result.findings) == 1
    assert "catastrophic failure" in result.findings[0].message
    assert result.findings[0].severity == "error"
    assert result.findings[0].stage == "exploding"


async def test_exception_result_has_duration() -> None:
    result = await ExplodingStage().run(make_action())
    assert result.duration_ms >= 0


async def test_supports_language_default_true() -> None:
    stage = AlwaysPassStage()
    assert stage.supports_language("python") is True
    assert stage.supports_language("typescript") is True
