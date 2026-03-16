"""Integration checks for JS/TS stage coverage."""

from __future__ import annotations

import pytest

from detent.stages.lint import LintStage
from detent.stages.syntax import SyntaxStage
from detent.stages.typecheck import TypecheckStage
from tests.conftest import make_action


@pytest.mark.asyncio
async def test_syntax_stage_handles_js_and_ts(tmp_path) -> None:
    stage = SyntaxStage()
    js_action = make_action(file_path=str(tmp_path / "app.js"), content="function foo() { return 1; }\n")
    ts_action = make_action(file_path=str(tmp_path / "app.ts"), content="const x: number = 1;\n")

    js_result = await stage.run(js_action)
    ts_result = await stage.run(ts_action)
    assert js_result.passed
    assert ts_result.passed


@pytest.mark.asyncio
async def test_syntax_stage_reports_invalid_js(tmp_path) -> None:
    stage = SyntaxStage()
    bad_action = make_action(file_path=str(tmp_path / "bad.js"), content="function () {\n")
    result = await stage.run(bad_action)
    assert not result.passed
    assert len(result.findings) > 0


@pytest.mark.asyncio
async def test_lint_stage_warns_without_eslint(tmp_path) -> None:
    stage = LintStage()
    action = make_action(file_path=str(tmp_path / "file.js"), content="console.log('x');\n")
    result = await stage.run(action)
    assert any("No ESLint config" in f.message for f in result.findings)


@pytest.mark.asyncio
async def test_typecheck_stage_warns_without_tsconfig(tmp_path) -> None:
    stage = TypecheckStage()
    action = make_action(file_path=str(tmp_path / "app.ts"), content="const x: number = 1;\n")
    result = await stage.run(action)
    assert any("No tsconfig.json" in f.message for f in result.findings)
