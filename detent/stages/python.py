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

"""Python language helpers -- ruff, mypy, and pytest async runners.

These standalone async functions are extracted from lint.py, typecheck.py, and
tests.py so that future language-dispatching stages can call them directly
without depending on the stage class hierarchy.

Each function accepts a ``stage_name`` parameter that is embedded in every
``Finding.stage`` field and used in log messages, allowing callers to present
findings under whatever stage name they choose.
"""

from __future__ import annotations

import asyncio
import contextlib
import glob as _glob
import json
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Literal

from detent.pipeline.result import Finding

logger = logging.getLogger(__name__)

_MAX_WALK_DEPTH = 5
_PASSING_EXIT_CODES = frozenset({0, 5})  # 0=all passed, 5=no tests collected

_MYPY_SEVERITY_MAP: dict[str, Literal["error", "warning", "info"]] = {
    "error": "error",
    "warning": "warning",
    "note": "info",
}


# ---------------------------------------------------------------------------
# Ruff
# ---------------------------------------------------------------------------


async def run_ruff(
    file_path: str,
    content: str,
    stage_name: str,
    timeout: float = 30,
) -> list[Finding]:
    """Lint *content* with ``ruff check`` via stdin.

    Uses ``--stdin-filename`` so Ruff resolves the correct config for the real
    path while reading from stdin (no temp file).  Returns an empty list when
    Ruff is not installed.

    Args:
        file_path: The real path of the file being linted (used as --stdin-filename).
        content: The source code to lint.
        stage_name: Embedded in every returned Finding's ``stage`` field.
        timeout: Subprocess timeout in seconds.

    Returns:
        List of :class:`Finding` objects; empty means clean.
    """
    logger.debug("[%s] running ruff on %s (%d bytes)", stage_name, file_path, len(content))

    try:
        proc = await asyncio.wait_for(
            asyncio.create_subprocess_exec(
                "ruff",
                "check",
                "--output-format",
                "json",
                "--stdin-filename",
                file_path,
                "-",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ),
            timeout=timeout,
        )
        stdout, stderr = await asyncio.wait_for(
            proc.communicate(input=content.encode("utf-8")),
            timeout=timeout,
        )
    except FileNotFoundError:
        logger.warning("[%s] ruff not found; skipping lint", stage_name)
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message="ruff is not installed; lint skipped",
                code="tool-not-found",
                stage=stage_name,
                fix_suggestion="Install ruff: pip install ruff",
            )
        ]
    except TimeoutError:
        logger.warning("[%s] ruff timed out after %ss", stage_name, timeout)
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"ruff timed out after {timeout}s",
                code="tool-timeout",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    if proc.returncode == 2:
        error_msg = stderr.decode("utf-8", errors="replace").strip()
        logger.error("[%s] ruff error: %s", stage_name, error_msg)
        return [
            Finding(
                severity="error",
                file=file_path,
                line=None,
                column=None,
                message=f"Ruff failed: {error_msg}",
                code="ruff-internal-error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    raw_output = stdout.decode("utf-8", errors="replace").strip()
    try:
        raw_findings: list[dict[str, Any]] = json.loads(raw_output) if raw_output else []
    except json.JSONDecodeError:
        logger.warning("[%s] ruff output was not valid JSON: %s", stage_name, raw_output[:200])
        raw_findings = []

    findings = [_parse_ruff_finding(f, stage_name) for f in raw_findings]
    logger.debug("[%s] ruff found %d finding(s)", stage_name, len(findings))
    return findings


def _parse_ruff_finding(raw: dict[str, Any], stage_name: str) -> Finding:
    """Convert a single Ruff JSON finding to a :class:`Finding`.

    Ruff code prefix to severity mapping:
    - ``W`` (pycodestyle warnings) maps to ``"warning"``
    - ``I`` (isort, informational) maps to ``"info"``
    - Everything else maps to ``"error"``
    """
    location = raw.get("location", {})
    code = raw.get("code") or ""
    if code.startswith("W"):
        severity: Literal["error", "warning", "info"] = "warning"
    elif code.startswith("I"):
        severity = "info"
    else:
        severity = "error"
    return Finding(
        severity=severity,
        file=raw.get("filename", ""),
        line=location.get("row"),
        column=location.get("column"),
        message=raw.get("message", ""),
        code=code or None,
        stage=stage_name,
        fix_suggestion=None,
    )


# ---------------------------------------------------------------------------
# mypy
# ---------------------------------------------------------------------------


async def run_mypy(
    file_path: str,
    content: str,
    stage_name: str,
    timeout: float = 30,
) -> list[Finding]:
    """Type-check *content* with ``mypy --output=json`` via a temp file.

    mypy does not support stdin, so content is written to a temp ``.py`` file,
    mypy is run on it, then the temp file is deleted.  The temp file path is
    remapped back to *file_path* in all returned findings.

    Args:
        file_path: The real path of the file being checked (used in findings).
        content: The source code to type-check.
        stage_name: Embedded in every returned Finding's ``stage`` field.
        timeout: Subprocess timeout in seconds.

    Returns:
        List of :class:`Finding` objects with ``"info"`` severity filtered out;
        empty means clean.
    """
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".py")
    try:
        with os.fdopen(tmp_fd, "w") as f:
            f.write(content)
        tmp_fd = -1  # fd is now owned by the file object; don't close again

        logger.debug("[%s] running mypy on %s (temp: %s)", stage_name, file_path, tmp_path)

        try:
            proc = await asyncio.wait_for(
                asyncio.create_subprocess_exec(
                    "mypy",
                    "--output=json",
                    "--no-error-summary",
                    "--ignore-missing-imports",
                    tmp_path,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                ),
                timeout=timeout,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except FileNotFoundError:
            logger.warning("[%s] mypy not found; skipping typecheck", stage_name)
            return [
                Finding(
                    severity="warning",
                    file=file_path,
                    line=None,
                    column=None,
                    message="mypy is not installed; typecheck skipped",
                    code="tool-not-found",
                    stage=stage_name,
                    fix_suggestion="Install mypy: pip install mypy",
                )
            ]
        except TimeoutError:
            logger.warning("[%s] mypy timed out after %ss", stage_name, timeout)
            return [
                Finding(
                    severity="warning",
                    file=file_path,
                    line=None,
                    column=None,
                    message=f"mypy timed out after {timeout}s",
                    code="tool-timeout",
                    stage=stage_name,
                    fix_suggestion=None,
                )
            ]

    finally:
        if tmp_fd != -1:
            with contextlib.suppress(OSError):
                os.close(tmp_fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)

    raw_output = stdout.decode("utf-8", errors="replace").strip()
    findings: list[Finding] = []
    for line in raw_output.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            raw: dict[str, Any] = json.loads(line)
            findings.append(_parse_mypy_finding(raw, file_path, stage_name))
        except json.JSONDecodeError:
            logger.debug("[%s] non-JSON mypy output: %s", stage_name, line)

    # Filter out "info" (mypy "note" severity) -- contextual hints, not type errors
    findings = [f for f in findings if f.severity != "info"]
    logger.debug("[%s] mypy found %d finding(s)", stage_name, len(findings))
    return findings


def _parse_mypy_finding(raw: dict[str, Any], original_path: str, stage_name: str) -> Finding:
    """Convert a single mypy JSON finding to a :class:`Finding`.

    Always uses *original_path* as the file (temp file path is discarded).
    mypy col is 0-indexed; kept as-is since Finding has no convention.
    mypy severity ``"note"`` is mapped to ``"info"`` and then filtered by the caller.
    """
    severity = _MYPY_SEVERITY_MAP.get(raw.get("severity", "error"), "error")
    return Finding(
        severity=severity,
        file=original_path,
        line=raw.get("line"),
        column=raw.get("col"),
        message=raw.get("message", ""),
        code=raw.get("code"),
        stage=stage_name,
        fix_suggestion=None,
    )


# ---------------------------------------------------------------------------
# pytest
# ---------------------------------------------------------------------------


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
