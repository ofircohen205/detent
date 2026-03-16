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

"""JavaScript/TypeScript lint helper -- ESLint async runner."""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Literal

from detent.config.languages import ESLINT_CONFIG_FILES
from detent.pipeline.result import Finding
from detent.stages._subprocess import cleanup_process as _cleanup

logger = logging.getLogger(__name__)


def _find_eslint_config(file_path: str) -> Path | None:
    """Walk up from file_path until an ESLint config file or package.json is found."""
    current = Path(file_path).resolve().parent
    while True:
        for candidate in ESLINT_CONFIG_FILES:
            config_path = current / candidate
            if config_path.exists():
                return config_path
        if (current / "package.json").exists():
            break
        if current.parent == current:
            break
        current = current.parent
    return None


def _parse_eslint_result(file_path: str, result: dict[str, list[dict[str, Any]]], stage_name: str) -> list[Finding]:
    """Convert a single ESLint result object into a list of Findings."""
    findings: list[Finding] = []
    for message in result.get("messages", []):
        level = message.get("severity", 2)
        severity: Literal["error", "warning"] = "error" if level == 2 else "warning"
        rule_id = message.get("ruleId") or "parse-error"
        findings.append(
            Finding(
                severity=severity,
                file=file_path,
                line=message.get("line"),
                column=message.get("column"),
                message=message.get("message", ""),
                code=f"eslint/{rule_id}",
                stage=stage_name,
                fix_suggestion=None,
            )
        )
    return findings


async def run_eslint(file_path: str, content: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run ESLint on file_path and return normalised Findings.

    Args:
        file_path: Absolute path to the JS/TS file being verified.
        content: File content (passed via stdin to ESLint).
        stage_name: Stage name to embed in each Finding (e.g. "lint").
        timeout: Seconds before the subprocess is killed.
    """
    config = _find_eslint_config(file_path)
    if config is None:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"No ESLint config found — skipping lint for {file_path}",
                code="eslint/no-config",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    try:
        proc = await asyncio.create_subprocess_exec(
            "eslint",
            "--format",
            "json",
            "--stdin",
            "--stdin-filename",
            file_path,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message="eslint not found — install with: npm install -D eslint",
                code="eslint/not-installed",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        await _cleanup(proc)
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"eslint timed out after {timeout}s",
                code="eslint/timeout",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    await _cleanup(proc)

    if proc.returncode is None:
        return []

    if proc.returncode == 0:
        return []

    if proc.returncode != 1:
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"eslint exited with code {proc.returncode} — stderr: {stderr_text[:200]}",
                code="eslint/error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    stdout_text = stdout.decode("utf-8", errors="replace").strip()
    if not stdout_text:
        return []

    try:
        parsed = json.loads(stdout_text)
    except json.JSONDecodeError:
        logger.warning("[javascript] eslint output was not valid JSON: %s", stdout_text[:200])
        return []

    findings: list[Finding] = []
    for result in parsed:
        findings.extend(_parse_eslint_result(file_path, result, stage_name))
    return findings
