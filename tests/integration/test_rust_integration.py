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

"""Integration tests for Rust verification stages (require cargo installed)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from detent.stages.rust import run_check, run_clippy
from detent.stages.syntax import SyntaxStage
from tests.conftest import make_action

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo not installed")


@pytest.fixture
def rust_crate(tmp_path: Path) -> Path:
    """Create a minimal Rust crate structure."""
    (tmp_path / "Cargo.toml").write_text('[package]\nname = "test_crate"\nversion = "0.1.0"\nedition = "2021"\n')
    (tmp_path / "src").mkdir()
    return tmp_path


VALID_RUST = "fn main() {}\n"
SYNTAX_ERROR_RUST = "fn main( {\n"
TYPE_ERROR_RUST = 'fn main() {\n    let x: i32 = "not an int";\n    let _ = x;\n}\n'


@pytest.mark.asyncio
async def test_syntax_stage_valid_rust_passes() -> None:
    """Test that valid Rust code passes syntax validation."""
    stage = SyntaxStage()
    action = make_action(file_path="/tmp/main.rs", content=VALID_RUST)
    result = await stage.run(action)
    assert result.passed
    assert result.findings == []


@pytest.mark.asyncio
async def test_syntax_stage_invalid_rust_fails() -> None:
    """Test that invalid Rust code fails syntax validation."""
    stage = SyntaxStage()
    action = make_action(file_path="/tmp/main.rs", content=SYNTAX_ERROR_RUST)
    result = await stage.run(action)
    assert not result.passed
    assert len(result.findings) > 0


@pytest.mark.asyncio
async def test_run_check_type_error_returns_error_finding(rust_crate: Path) -> None:
    """Test that type errors in Rust code produce error findings."""
    file_path = str(rust_crate / "src" / "main.rs")
    findings = await run_check(file_path, TYPE_ERROR_RUST, "typecheck", 60)
    assert any(f.severity == "error" for f in findings)
    assert all(f.file == file_path for f in findings if f.severity == "error")


@pytest.mark.asyncio
async def test_run_check_valid_rust_returns_empty(rust_crate: Path) -> None:
    """Test that valid Rust code produces no findings."""
    file_path = str(rust_crate / "src" / "main.rs")
    findings = await run_check(file_path, VALID_RUST, "typecheck", 60)
    assert findings == []


@pytest.mark.asyncio
async def test_run_clippy_valid_returns_empty(rust_crate: Path) -> None:
    """Test that clippy produces no findings for valid code."""
    file_path = str(rust_crate / "src" / "main.rs")
    findings = await run_clippy(file_path, VALID_RUST, "lint", 60)
    assert findings == []
