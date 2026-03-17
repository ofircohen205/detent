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

"""Python lint helper -- ruff async runner."""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

import structlog

from detent.pipeline.result import Finding

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


async def run_ruff(
    file_path: str,
    content: str,
    stage_name: str,
    timeout: float = 30,
) -> list[Finding]:
    """Lint *content* with ``ruff check`` via stdin."""
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
    """Convert a single Ruff JSON finding to a :class:`Finding`."""
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
