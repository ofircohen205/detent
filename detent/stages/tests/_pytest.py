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

"""Python tests helper -- pytest async runner."""

from __future__ import annotations

import asyncio
import glob as _glob
import sys
from pathlib import Path

import structlog

from detent.pipeline.result import Finding

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_MAX_WALK_DEPTH = 5
_PASSING_EXIT_CODES = frozenset({0, 5})  # 0=all passed, 5=no tests collected


async def run_pytest(
    file_path: str,
    stage_name: str,
    timeout: float = 30,
) -> list[Finding]:
    """Discover and run pytest test files related to *file_path*.

    Uses :func:`_find_test_files` to locate related tests.  If none are found,
    returns an empty list (caller should treat as skipped).

    Args:
        file_path: Source file whose related tests should be run.
        stage_name: Embedded in every returned Finding's ``stage`` field.
        timeout: Subprocess timeout in seconds.

    Returns:
        List of :class:`Finding` objects; empty means all tests passed (or no
        tests were found).
    """
    test_files = _find_test_files(file_path)
    if not test_files:
        logger.debug("[%s] no test files found for %s", stage_name, file_path)
        return []

    logger.debug("[%s] running pytest on %s", stage_name, [str(f) for f in test_files])

    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                sys.executable,
                "-m",
                "pytest",
                *[str(f) for f in test_files],
                "--tb=short",
                "-q",
                "--no-header",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=timeout,
        )
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except FileNotFoundError:
        logger.warning("[%s] pytest not found; skipping tests", stage_name)
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message="pytest is not installed; tests skipped",
                code="tool-not-found",
                stage=stage_name,
                fix_suggestion="Install pytest: pip install pytest",
            )
        ]
    except TimeoutError:
        logger.warning("[%s] pytest timed out after %ss", stage_name, timeout)
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"pytest timed out after {timeout}s",
                code="tool-timeout",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    output = stdout.decode("utf-8", errors="replace")
    passed = proc.returncode in _PASSING_EXIT_CODES
    if not passed and stderr:
        logger.debug(
            "[%s] pytest stderr: %s",
            stage_name,
            stderr.decode("utf-8", errors="replace").strip(),
        )

    if passed:
        return []

    findings = _parse_pytest_failures(output, file_path, stage_name)
    logger.debug("[%s] pytest found %d failure(s)", stage_name, len(findings))
    return findings


def _find_test_files(file_path: str) -> list[Path]:
    """Find test files related to *file_path*.

    Walks up from the source file's directory at most :data:`_MAX_WALK_DEPTH`
    levels, looking for a ``tests/`` directory, then searches for files named
    ``test_{stem}.py`` inside it.

    Only ``.py`` source files are supported; all others return an empty list.
    """
    path = Path(file_path)
    if path.suffix != ".py":
        return []

    stem = path.stem
    candidate = path.parent

    for _ in range(_MAX_WALK_DEPTH):
        tests_dir = candidate / "tests"
        if tests_dir.is_dir():
            matches = list(tests_dir.rglob(f"test_{_glob.escape(stem)}.py"))
            if matches:
                return matches
        parent = candidate.parent
        if parent == candidate:
            break
        candidate = parent

    return []


def _parse_pytest_failures(output: str, file_path: str, stage_name: str) -> list[Finding]:
    """Extract failed test names from ``pytest --tb=short -q`` output.

    Lines starting with ``'FAILED '`` contain the test node ID followed by
    ``' - '`` and the error message.
    """
    findings = []
    for line in output.splitlines():
        if line.startswith("FAILED "):
            parts = line[7:].split(" - ", 1)
            test_name = parts[0].strip()
            error_detail = parts[1].strip() if len(parts) > 1 else ""
            message = f"Test failed: {test_name}"
            if error_detail:
                message += f" \u2014 {error_detail}"
            findings.append(
                Finding(
                    severity="error",
                    file=file_path,
                    line=None,
                    column=None,
                    message=message,
                    code=None,
                    stage=stage_name,
                    fix_suggestion=None,
                )
            )
    return findings
