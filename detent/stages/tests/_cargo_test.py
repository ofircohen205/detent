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

"""Rust tests helper -- cargo test async runner."""

from __future__ import annotations

import logging
import re

from detent.pipeline.result import Finding
from detent.stages.languages._rust import (
    _no_cargo_finding,
    _not_found_finding,
    _run_cargo,
    find_crate_root,
)

logger = logging.getLogger(__name__)

_FAIL_RE = re.compile(r"^test\s+(\S+)\s+\.\.\.\s+FAILED$")


async def run_test(file_path: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run cargo test -p <crate> and return findings for failed tests."""
    info = find_crate_root(file_path)
    if info is None:
        return [_no_cargo_finding(file_path, stage_name)]
    crate_root, crate_name = info
    logger.debug("[%s] cargo test -p %s (cwd=%s)", stage_name, crate_name, crate_root)
    try:
        stdout, stderr, rc = await _run_cargo(
            ["cargo", "test", "-p", crate_name],
            crate_root,
            timeout,
        )
    except FileNotFoundError:
        return [_not_found_finding(file_path, stage_name)]
    except TimeoutError:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"cargo test timed out after {timeout}s",
                code="cargo/timeout",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]
    logger.debug("[%s] cargo test returncode=%s", stage_name, rc)
    if rc == 101:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"cargo test binary compile error: {stderr.decode('utf-8', errors='replace').strip()[:200]}",
                code="cargo/test-compile-error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]
    if rc == 0:
        return []
    return _parse_cargo_test_output(stdout.decode("utf-8", errors="replace"), file_path, stage_name)


def _parse_cargo_test_output(output: str, file_path: str, stage_name: str) -> list[Finding]:
    """Parse cargo test stdout for FAILED test lines."""
    findings = []
    for line in output.splitlines():
        if "running 0 tests" in line:
            return []
        m = _FAIL_RE.match(line.strip())
        if m:
            findings.append(
                Finding(
                    severity="error",
                    file=file_path,
                    line=None,
                    column=None,
                    message=f"Test failed: {m.group(1)}",
                    code="cargo/test-failed",
                    stage=stage_name,
                    fix_suggestion=None,
                )
            )
    return findings
