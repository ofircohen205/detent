"""Tests for SyntaxStage — tree-sitter Python syntax validation."""

from __future__ import annotations

import pytest

from detent.stages.syntax import SyntaxStage
from tests.conftest import make_action


@pytest.fixture
def stage() -> SyntaxStage:
    return SyntaxStage()


async def test_valid_python_passes(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.py", content='def hello():\n    return "hi"\n')
    result = await stage.run(action)
    assert result.passed
    assert result.findings == []
    assert result.stage == "syntax"


async def test_invalid_syntax_fails(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.py", content="def hello(\n    return 'missing paren'\n")
    result = await stage.run(action)
    assert not result.passed
    assert len(result.findings) > 0
    assert result.findings[0].severity == "error"


async def test_finding_has_line_number(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.py", content="def hello(\n    return 'missing paren'\n")
    result = await stage.run(action)
    assert result.findings[0].line is not None
    assert result.findings[0].line >= 1


async def test_finding_has_original_file_path(stage: SyntaxStage) -> None:
    action = make_action(file_path="/project/src/main.py", content="def bad(:\n    pass\n")
    result = await stage.run(action)
    assert result.findings[0].file == "/project/src/main.py"


async def test_unsupported_extension_skips(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.rb", content='puts "hello"')
    result = await stage.run(action)
    assert result.passed
    assert result.metadata.get("skipped") is True


async def test_empty_content_passes(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.py", content="")
    result = await stage.run(action)
    assert result.passed


async def test_result_has_duration(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.py", content="x = 1\n")
    result = await stage.run(action)
    assert result.duration_ms >= 0


async def test_stage_name_is_syntax(stage: SyntaxStage) -> None:
    assert stage.name == "syntax"


async def test_supports_python(stage: SyntaxStage) -> None:
    assert stage.supports_language("python") is True


async def test_supports_typescript(stage: SyntaxStage) -> None:
    assert stage.supports_language("typescript") is True


async def test_supports_go(stage: SyntaxStage) -> None:
    assert stage.supports_language("go") is True


async def test_supports_rust(stage: SyntaxStage) -> None:
    assert stage.supports_language("rust") is True


async def test_does_not_support_py_alias(stage: SyntaxStage) -> None:
    # Pipeline always sends "python", not "py"
    assert stage.supports_language("py") is False


async def test_valid_go_passes(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.go", content="package main\n\nfunc main() {}\n")
    result = await stage.run(action)
    assert result.passed
    assert result.findings == []


async def test_invalid_go_fails(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.go", content="package main\n\nfunc main( {\n")
    result = await stage.run(action)
    assert not result.passed
    assert len(result.findings) > 0


async def test_valid_rust_passes(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.rs", content="fn main() {}\n")
    result = await stage.run(action)
    assert result.passed
    assert result.findings == []


async def test_invalid_rust_fails(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.rs", content="fn main( {\n")
    result = await stage.run(action)
    assert not result.passed
    assert len(result.findings) > 0
