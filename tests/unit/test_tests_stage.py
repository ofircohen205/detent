"""Tests for TestsStage — pytest execution for files related to the modified source."""

from __future__ import annotations

from pathlib import Path

import pytest

from detent.stages.tests import TestsStage
from tests.conftest import make_action


@pytest.fixture
def stage() -> TestsStage:
    return TestsStage()


async def test_no_test_file_skips(stage: TestsStage, tmp_path: Path) -> None:
    """If no test file can be found, the stage skips and returns passed."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "main.py").write_text("def hello(): return 1\n")
    action = make_action(file_path=str(src / "main.py"), content="def hello(): return 1\n")
    result = await stage.run(action)
    assert result.passed
    assert result.metadata.get("skipped") is True


async def test_passing_tests_pass(stage: TestsStage, tmp_path: Path) -> None:
    """When the related test file exists and all tests pass, stage passes."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_calc.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, '{tmp_path}')\n"
        "from src.calc import add\n\n"
        "def test_add():\n"
        "    assert add(1, 2) == 3\n"
    )

    action = make_action(
        file_path=str(src / "calc.py"),
        content="def add(a: int, b: int) -> int:\n    return a + b\n",
    )
    result = await stage.run(action)
    assert result.passed
    assert result.findings == []


async def test_failing_tests_fail(stage: TestsStage, tmp_path: Path) -> None:
    """When the related test file exists and a test fails, stage fails."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_calc.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, '{tmp_path}')\n"
        "from src.calc import add\n\n"
        "def test_add_wrong():\n"
        "    assert add(1, 2) == 99\n"
    )

    action = make_action(
        file_path=str(src / "calc.py"),
        content="def add(a: int, b: int) -> int:\n    return a + b\n",
    )
    result = await stage.run(action)
    assert not result.passed


async def test_failing_tests_produce_findings(stage: TestsStage, tmp_path: Path) -> None:
    """Failing tests are reported as error findings."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "calc.py").write_text("def add(a: int, b: int) -> int:\n    return a + b\n")

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_calc.py").write_text(
        "import sys\n"
        f"sys.path.insert(0, '{tmp_path}')\n"
        "from src.calc import add\n\n"
        "def test_add_wrong():\n"
        "    assert add(1, 2) == 99\n"
    )

    action = make_action(
        file_path=str(src / "calc.py"),
        content="def add(a: int, b: int) -> int:\n    return a + b\n",
    )
    result = await stage.run(action)
    assert len(result.findings) > 0
    assert result.findings[0].severity == "error"
    assert "test_add_wrong" in result.findings[0].message


async def test_stage_name_is_tests(stage: TestsStage) -> None:
    assert stage.name == "tests"


async def test_no_file_path_skips(stage: TestsStage) -> None:
    """If action has no file_path, skip gracefully."""
    action = make_action(file_path="", content="x = 1")
    result = await stage.run(action)
    assert result.passed
    assert result.metadata.get("skipped") is True
