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

"""Integration tests for Go verification stages (require go installed)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from detent.stages.go import run_build, run_vet
from detent.stages.syntax import SyntaxStage
from tests.conftest import make_action

pytestmark = pytest.mark.skipif(shutil.which("go") is None, reason="go not installed")


@pytest.fixture
def go_module(tmp_path: Path) -> Path:
    """Create a minimal Go module structure."""
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
    return tmp_path


VALID_GO = "package main\n\nfunc main() {}\n"
SYNTAX_ERROR_GO = "package main\n\nfunc main( {\n"
TYPE_ERROR_GO = 'package main\n\nfunc main() {\n\tvar x int = "not an int"\n\t_ = x\n}\n'


@pytest.mark.asyncio
async def test_syntax_stage_valid_go_passes() -> None:
    """Test that valid Go code passes syntax validation."""
    stage = SyntaxStage()
    action = make_action(file_path="/tmp/main.go", content=VALID_GO)
    result = await stage.run(action)
    assert result.passed
    assert result.findings == []


@pytest.mark.asyncio
async def test_syntax_stage_invalid_go_fails() -> None:
    """Test that invalid Go code fails syntax validation."""
    stage = SyntaxStage()
    action = make_action(file_path="/tmp/main.go", content=SYNTAX_ERROR_GO)
    result = await stage.run(action)
    assert not result.passed
    assert len(result.findings) > 0
    assert result.findings[0].severity == "error"


@pytest.mark.asyncio
async def test_run_build_type_error_returns_error_finding(go_module: Path) -> None:
    """Test that type errors in Go code produce error findings."""
    file_path = str(go_module / "main.go")
    findings = await run_build(file_path, TYPE_ERROR_GO, "typecheck", 30)
    assert any(f.severity == "error" for f in findings)


@pytest.mark.asyncio
async def test_run_build_valid_go_returns_empty(go_module: Path) -> None:
    """Test that valid Go code produces no findings."""
    file_path = str(go_module / "main.go")
    findings = await run_build(file_path, VALID_GO, "typecheck", 30)
    assert findings == []


@pytest.mark.asyncio
async def test_run_vet_valid_returns_empty(go_module: Path) -> None:
    """Test that go vet produces no findings for valid code."""
    file_path = str(go_module / "main.go")
    findings = await run_vet(file_path, VALID_GO, "lint", 30)
    assert findings == []
