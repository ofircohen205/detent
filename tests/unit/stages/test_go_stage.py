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

"""Unit tests for detent.stages.go helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from detent.stages.languages._go import find_module_root
from detent.stages.lint import LintStage
from detent.stages.typecheck import TypecheckStage
from tests.conftest import make_action

# ---------------------------------------------------------------------------
# find_module_root tests (sync)
# ---------------------------------------------------------------------------


def test_find_module_root_finds_go_mod(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module example.com/mymod\n\ngo 1.21\n")
    src_dir = tmp_path / "internal" / "proxy"
    src_dir.mkdir(parents=True)
    assert find_module_root(str(src_dir / "handler.go")) == tmp_path


def test_find_module_root_returns_none_when_missing(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    assert find_module_root(str(tmp_path / "src" / "main.go")) is None


def test_find_module_root_finds_go_mod_in_parent(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n")
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert find_module_root(str(deep / "file.go")) == tmp_path


# ---------------------------------------------------------------------------
# run_vet tests
# ---------------------------------------------------------------------------


async def test_run_vet_go_not_installed(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n")
    file_path = str(tmp_path / "main.go")
    Path(file_path).write_text("package main\nfunc main() {}\n")
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        from detent.stages.lint._go_vet import run_vet

        findings = await run_vet(file_path, "package main\nfunc main() {}\n", "lint", 30)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert "go not found" in findings[0].message


async def test_run_vet_no_go_mod(tmp_path: Path) -> None:
    file_path = str(tmp_path / "main.go")
    from detent.stages.lint._go_vet import run_vet

    findings = await run_vet(file_path, "package main\n", "lint", 30)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert "go.mod" in findings[0].message


async def test_run_vet_clean_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n")
    file_path = str(tmp_path / "main.go")
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from detent.stages.lint._go_vet import run_vet

        findings = await run_vet(file_path, "package main\n", "lint", 30)
    assert findings == []


async def test_run_vet_returns_warning_findings(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n")
    file_path = str(tmp_path / "main.go")
    stderr = b"main.go:5:2: x declared and not used\n"
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", stderr))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from detent.stages.lint._go_vet import run_vet

        findings = await run_vet(file_path, "package main\n", "lint", 30)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].file == file_path


# ---------------------------------------------------------------------------
# run_build tests
# ---------------------------------------------------------------------------


async def test_run_build_compile_error_returns_error_finding(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n")
    file_path = str(tmp_path / "main.go")
    stderr = b"main.go:3:5: undefined: fmt\n"
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(b"", stderr))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from detent.stages.typecheck._go_build import run_build

        findings = await run_build(file_path, "package main\n", "typecheck", 30)
    assert len(findings) == 1
    assert findings[0].severity == "error"


# ---------------------------------------------------------------------------
# run_test tests
# ---------------------------------------------------------------------------


async def test_run_test_no_go_mod(tmp_path: Path) -> None:
    file_path = str(tmp_path / "main.go")
    from detent.stages.tests._go_test import run_test

    findings = await run_test(file_path, "tests", 30)
    assert len(findings) == 1
    assert findings[0].severity == "warning"


async def test_run_test_no_test_files_returns_empty(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n")
    file_path = str(tmp_path / "main.go")
    stdout = b'{"Action":"output","Output":"[no test files]\\n"}\n'
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(stdout, b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from detent.stages.tests._go_test import run_test

        findings = await run_test(file_path, "tests", 30)
    assert findings == []


async def test_run_test_failed_test_returns_error(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n")
    file_path = str(tmp_path / "main_test.go")
    stdout_lines = [
        json.dumps({"Action": "output", "Test": "TestFoo", "Output": "--- FAIL: TestFoo\n"}),
        json.dumps({"Action": "fail", "Test": "TestFoo"}),
    ]
    stdout = "\n".join(stdout_lines).encode()
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(stdout, b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from detent.stages.tests._go_test import run_test

        findings = await run_test(file_path, "tests", 30)
    assert len(findings) == 1
    assert "TestFoo" in findings[0].message
    assert findings[0].severity == "error"


# ---------------------------------------------------------------------------
# Stage dispatch tests
# ---------------------------------------------------------------------------


def test_lint_stage_supports_go() -> None:
    assert LintStage().supports_language("go") is True


def test_typecheck_stage_supports_go() -> None:
    assert TypecheckStage().supports_language("go") is True


async def test_lint_stage_dispatches_to_go_vet(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n")
    file_path = str(tmp_path / "main.go")
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        stage = LintStage()
        action = make_action(file_path=file_path, content="package main\n")
        result = await stage.run(action)
    assert result.metadata["tool"] == "go vet"
    assert result.metadata["language"] == "go"


async def test_typecheck_stage_dispatches_to_go_build(tmp_path: Path) -> None:
    (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n")
    file_path = str(tmp_path / "main.go")
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        stage = TypecheckStage()
        action = make_action(file_path=file_path, content="package main\n")
        result = await stage.run(action)
    assert result.metadata["tool"] == "go build"
    assert result.metadata["language"] == "go"
