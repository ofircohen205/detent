"""Tests for LintStage — Ruff linting via stdin."""

from __future__ import annotations

import pytest

from detent.stages.lint import LintStage
from tests.conftest import make_action


@pytest.fixture
def stage() -> LintStage:
    return LintStage()


async def test_clean_code_passes(stage: LintStage) -> None:
    action = make_action(file_path="/src/main.py", content="x = 1\n")
    result = await stage.run(action)
    assert result.passed
    assert result.findings == []


async def test_unused_import_fails(stage: LintStage) -> None:
    action = make_action(file_path="/src/main.py", content="import os\nx = 1\n")
    result = await stage.run(action)
    assert not result.passed
    assert len(result.findings) > 0


async def test_finding_has_code(stage: LintStage) -> None:
    action = make_action(file_path="/src/main.py", content="import os\nx = 1\n")
    result = await stage.run(action)
    assert any(f.code == "F401" for f in result.findings)


async def test_finding_has_original_file_path(stage: LintStage) -> None:
    action = make_action(file_path="/project/src/main.py", content="import os\nx = 1\n")
    result = await stage.run(action)
    assert result.findings[0].file == "/project/src/main.py"


async def test_finding_has_line_number(stage: LintStage) -> None:
    action = make_action(file_path="/src/main.py", content="import os\nx = 1\n")
    result = await stage.run(action)
    assert result.findings[0].line == 1


async def test_unsupported_extension_skips(stage: LintStage) -> None:
    action = make_action(file_path="/src/main.ts", content="const x = 1;")
    result = await stage.run(action)
    assert result.passed
    assert result.metadata.get("skipped") is True


async def test_stage_name_is_lint(stage: LintStage) -> None:
    assert stage.name == "lint"


async def test_result_has_duration(stage: LintStage) -> None:
    action = make_action(file_path="/src/main.py", content="x = 1\n")
    result = await stage.run(action)
    assert result.duration_ms >= 0


async def test_multiple_violations(stage: LintStage) -> None:
    action = make_action(file_path="/src/main.py", content="import os\nimport sys\nx = 1\n")
    result = await stage.run(action)
    assert not result.passed
    assert len(result.findings) >= 2
