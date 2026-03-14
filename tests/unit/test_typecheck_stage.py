"""Tests for TypecheckStage — mypy type checking via temp file."""

from __future__ import annotations

import pytest

from detent.stages.typecheck import TypecheckStage
from tests.conftest import make_action


@pytest.fixture
def stage() -> TypecheckStage:
    return TypecheckStage()


async def test_type_correct_code_passes(stage: TypecheckStage) -> None:
    action = make_action(file_path="/src/main.py", content="x: int = 1\n")
    result = await stage.run(action)
    assert result.passed
    assert result.findings == []


async def test_type_error_fails(stage: TypecheckStage) -> None:
    action = make_action(file_path="/src/main.py", content='x: int = "hello"\n')
    result = await stage.run(action)
    assert not result.passed
    assert len(result.findings) > 0


async def test_finding_severity_is_error(stage: TypecheckStage) -> None:
    action = make_action(file_path="/src/main.py", content='x: int = "hello"\n')
    result = await stage.run(action)
    assert result.findings[0].severity == "error"


async def test_finding_has_line_number(stage: TypecheckStage) -> None:
    action = make_action(file_path="/src/main.py", content='x: int = "hello"\n')
    result = await stage.run(action)
    assert result.findings[0].line == 1


async def test_finding_uses_original_file_path(stage: TypecheckStage) -> None:
    action = make_action(file_path="/project/src/main.py", content='x: int = "hello"\n')
    result = await stage.run(action)
    assert result.findings[0].file == "/project/src/main.py"
    assert "/tmp" not in result.findings[0].file


async def test_unsupported_extension_skips(stage: TypecheckStage) -> None:
    action = make_action(file_path="/src/main.go", content="package main\nfunc main() {}")
    result = await stage.run(action)
    assert result.passed
    assert result.metadata.get("skipped") is True


async def test_stage_name_is_typecheck(stage: TypecheckStage) -> None:
    assert stage.name == "typecheck"


async def test_result_has_duration(stage: TypecheckStage) -> None:
    action = make_action(file_path="/src/main.py", content="x: int = 1\n")
    result = await stage.run(action)
    assert result.duration_ms >= 0
