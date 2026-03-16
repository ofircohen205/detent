"""Tests for VerificationStage base class."""

from __future__ import annotations

import pytest

from detent.pipeline.result import VerificationResult
from detent.schema import AgentAction
from detent.stages.base import VerificationStage, _validate_file_path
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


def test_validate_file_path_rejects_dotdot() -> None:
    with pytest.raises(ValueError, match="traversal"):
        _validate_file_path("src/../../../etc/passwd")


def test_validate_file_path_rejects_null_byte() -> None:
    with pytest.raises(ValueError, match="null byte"):
        _validate_file_path("src/foo\x00bar.py")


def test_validate_file_path_rejects_glob_metachar() -> None:
    for bad in ["src/*.py", "src/fo?.py", "src/[foo].py"]:
        with pytest.raises(ValueError, match="glob"):
            _validate_file_path(bad)


def test_validate_file_path_accepts_normal_paths() -> None:
    for good in [
        "src/main.py",
        "/home/user/project/detent/detent/cli.py",
        "tests/unit/test_foo.py",
    ]:
        _validate_file_path(good)  # must not raise
