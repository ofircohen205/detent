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

"""Python typecheck helper -- mypy async runner."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile
from typing import Any, Literal

from detent.pipeline.result import Finding

logger = logging.getLogger(__name__)

_MYPY_SEVERITY_MAP: dict[str, Literal["error", "warning", "info"]] = {
    "error": "error",
    "warning": "warning",
    "note": "info",
}


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
