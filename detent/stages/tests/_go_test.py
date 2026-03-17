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

"""Go tests helper -- go test async runner."""

from __future__ import annotations

import asyncio
import contextlib
import json

import structlog

from detent.pipeline.result import Finding
from detent.stages.languages._go import (
    _no_mod_finding,
    _not_found_finding,
    _pkg_path,
    find_module_root,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


async def run_test(file_path: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run go test -json on the package containing file_path."""
    module_root = find_module_root(file_path)
    if module_root is None:
        return [_no_mod_finding(file_path, stage_name)]
    pkg = _pkg_path(file_path, module_root)
    logger.debug("[%s] go test -json %s (cwd=%s)", stage_name, pkg, module_root)
    try:
        proc = await asyncio.create_subprocess_exec(
            "go",
            "test",
            "-json",
            pkg,
            cwd=str(module_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return [_not_found_finding(file_path, stage_name)]
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.communicate()
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"go test timed out after {timeout}s",
                code="go/timeout",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]
    logger.debug("[%s] go test returncode=%s", stage_name, proc.returncode)
    if proc.returncode is not None and proc.returncode >= 2:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"go test build error: {stderr.decode('utf-8', errors='replace').strip()[:200]}",
                code="go/test-build-error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]
    return _parse_go_test_json(stdout, file_path, stage_name)


def _parse_go_test_json(stdout: bytes, file_path: str, stage_name: str) -> list[Finding]:
    """Parse go test -json output into findings."""
    output_cache: dict[str, list[str]] = {}
    findings: list[Finding] = []
    for raw_line in stdout.decode("utf-8", errors="replace").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            logger.debug("[%s] go test: malformed JSON: %s", stage_name, raw_line)
            continue
        action = obj.get("Action", "")
        test_name = obj.get("Test", "")
        output = obj.get("Output", "")
        if "[no test files]" in output:
            return []
        if action == "output" and test_name:
            output_cache.setdefault(test_name, []).append(output)
        elif action == "fail" and test_name:
            cached = "".join(output_cache.get(test_name, []))
            findings.append(
                Finding(
                    severity="error",
                    file=file_path,
                    line=None,
                    column=None,
                    message=f"Test failed: {test_name} — {cached.strip()[:300]}",
                    code="go/test-failed",
                    stage=stage_name,
                    fix_suggestion=None,
                )
            )
            output_cache.pop(test_name, None)
        elif action in ("pass", "skip") and test_name:
            output_cache.pop(test_name, None)
    return findings
