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

"""Unit tests for detent.stages.rust helpers."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from detent.stages.lint import LintStage
from detent.stages.tests import TestsStage
from detent.stages.typecheck import TypecheckStage
from tests.conftest import make_action


# find_crate_root tests (sync)
def test_find_crate_root_finds_cargo_toml(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "myapp"\nversion = "0.1.0"\n')
    src = tmp_path / "src"
    src.mkdir()
    from detent.stages.languages._rust import find_crate_root

    result = find_crate_root(str(src / "main.rs"))
    assert result is not None
    assert result[0] == tmp_path
    assert result[1] == "myapp"


def test_find_crate_root_returns_none_when_missing(tmp_path):
    (tmp_path / "src").mkdir()
    from detent.stages.languages._rust import find_crate_root

    assert find_crate_root(str(tmp_path / "src" / "main.rs")) is None


def test_find_crate_root_workspace_finds_member(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[workspace]\nmembers = ["crates/mylib"]\n')
    member = tmp_path / "crates" / "mylib"
    member.mkdir(parents=True)
    (member / "Cargo.toml").write_text('[package]\nname = "mylib"\nversion = "0.1.0"\n')
    src = member / "src"
    src.mkdir()
    from detent.stages.languages._rust import find_crate_root

    result = find_crate_root(str(src / "lib.rs"))
    assert result is not None
    assert result[1] == "mylib"


# run_clippy tests
async def test_run_clippy_cargo_not_installed(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\nversion = "0.1.0"\n')
    file_path = str(tmp_path / "src" / "main.rs")
    Path(tmp_path / "src").mkdir()
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        from detent.stages.lint._clippy import run_clippy

        findings = await run_clippy(file_path, "fn main() {}", "lint", 30)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert "cargo not found" in findings[0].message


async def test_run_clippy_no_cargo_toml(tmp_path):
    file_path = str(tmp_path / "main.rs")
    from detent.stages.lint._clippy import run_clippy

    findings = await run_clippy(file_path, "fn main() {}", "lint", 30)
    assert len(findings) == 1
    assert "Cargo.toml" in findings[0].message


async def test_run_clippy_clean_returns_empty(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\nversion = "0.1.0"\n')
    file_path = str(tmp_path / "src" / "main.rs")
    Path(tmp_path / "src").mkdir()
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from detent.stages.lint._clippy import run_clippy

        findings = await run_clippy(file_path, "fn main() {}", "lint", 30)
    assert findings == []


async def test_run_clippy_returns_warning_findings(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\nversion = "0.1.0"\n')
    file_path = str(tmp_path / "src" / "main.rs")
    Path(tmp_path / "src").mkdir()
    compiler_msg = {
        "reason": "compiler-message",
        "message": {
            "level": "warning",
            "message": "unused variable: `x`",
            "code": {"code": "unused_variables"},
            "spans": [{"is_primary": True, "line_start": 2, "column_start": 5}],
        },
    }
    stdout = json.dumps(compiler_msg).encode() + b"\n"
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(stdout, b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from detent.stages.lint._clippy import run_clippy

        findings = await run_clippy(file_path, "fn main() {}", "lint", 30)
    assert len(findings) == 1
    assert findings[0].severity == "warning"
    assert findings[0].line == 2
    assert findings[0].file == file_path


# run_check tests
async def test_run_check_error_finding(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\nversion = "0.1.0"\n')
    file_path = str(tmp_path / "src" / "main.rs")
    Path(tmp_path / "src").mkdir()
    compiler_msg = {
        "reason": "compiler-message",
        "message": {
            "level": "error",
            "message": "mismatched types",
            "code": {"code": "E0308"},
            "spans": [{"is_primary": True, "line_start": 3, "column_start": 10}],
        },
    }
    stdout = json.dumps(compiler_msg).encode() + b"\n"
    mock_proc = MagicMock()
    mock_proc.returncode = 1
    mock_proc.communicate = AsyncMock(return_value=(stdout, b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from detent.stages.typecheck._cargo_check import run_check

        findings = await run_check(file_path, "fn main() {}", "typecheck", 30)
    assert len(findings) == 1
    assert findings[0].severity == "error"


# run_test tests
async def test_run_test_no_cargo_toml(tmp_path):
    file_path = str(tmp_path / "main.rs")
    from detent.stages.tests._cargo_test import run_test

    findings = await run_test(file_path, "tests", 30)
    assert len(findings) == 1
    assert findings[0].severity == "warning"


async def test_run_test_all_pass_returns_empty(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\nversion = "0.1.0"\n')
    file_path = str(tmp_path / "src" / "main.rs")
    Path(tmp_path / "src").mkdir()
    stdout = b"running 2 tests\ntest it_works ... ok\ntest result: ok. 2 passed; 0 failed;\n"
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(stdout, b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from detent.stages.tests._cargo_test import run_test

        findings = await run_test(file_path, "tests", 30)
    assert findings == []


async def test_run_test_failed_test_returns_error(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\nversion = "0.1.0"\n')
    file_path = str(tmp_path / "src" / "main.rs")
    Path(tmp_path / "src").mkdir()
    stdout = b"running 1 test\ntest it_fails ... FAILED\ntest result: FAILED. 0 passed; 1 failed;\n"
    mock_proc = MagicMock()
    mock_proc.returncode = 101
    mock_proc.communicate = AsyncMock(return_value=(stdout, b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        from detent.stages.tests._cargo_test import run_test

        findings = await run_test(file_path, "tests", 30)
    # returncode=101 is treated as compile error warning, not test failures
    assert len(findings) == 1
    assert findings[0].severity == "warning"

    # Test with returncode=1 for actual test failure
    mock_proc2 = MagicMock()
    mock_proc2.returncode = 1
    mock_proc2.communicate = AsyncMock(return_value=(stdout, b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc2):
        findings2 = await run_test(file_path, "tests", 30)
    assert len(findings2) == 1
    assert "it_fails" in findings2[0].message
    assert findings2[0].severity == "error"


# Stage dispatch tests
def test_lint_stage_supports_rust():
    assert LintStage().supports_language("rust") is True


def test_typecheck_stage_supports_rust():
    assert TypecheckStage().supports_language("rust") is True


def test_tests_stage_supports_rust():
    assert TestsStage().supports_language("rust") is True


async def test_lint_stage_dispatches_to_clippy(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\nversion = "0.1.0"\n')
    file_path = str(tmp_path / "src" / "main.rs")
    Path(tmp_path / "src").mkdir()
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        stage = LintStage()
        action = make_action(file_path=file_path, content="fn main() {}")
        result = await stage.run(action)
    assert result.metadata["tool"] == "cargo clippy"
    assert result.metadata["language"] == "rust"


async def test_typecheck_stage_dispatches_to_check(tmp_path):
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "app"\nversion = "0.1.0"\n')
    file_path = str(tmp_path / "src" / "main.rs")
    Path(tmp_path / "src").mkdir()
    mock_proc = MagicMock()
    mock_proc.returncode = 0
    mock_proc.communicate = AsyncMock(return_value=(b"", b""))
    with patch("asyncio.create_subprocess_exec", return_value=mock_proc):
        stage = TypecheckStage()
        action = make_action(file_path=file_path, content="fn main() {}")
        result = await stage.run(action)
    assert result.metadata["tool"] == "cargo check"
    assert result.metadata["language"] == "rust"
