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

"""Consolidated JS/TS helpers: ESLint (lint), tsc (typecheck), Jest/Vitest (tests)."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from pathlib import Path
from typing import Any

from detent.config.languages import ESLINT_CONFIG_FILES, TS_CONFIG_FILENAME
from detent.pipeline.result import Finding

logger = logging.getLogger(__name__)

_TSC_PATTERN = re.compile(r"^(.+)\((\d+),(\d+)\): (error|warning) (TS\d+): (.+)$")

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _cleanup(proc: asyncio.subprocess.Process) -> None:
    """Kill a subprocess if still running and await it."""
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.communicate()


# ---------------------------------------------------------------------------
# ESLint (lint)
# ---------------------------------------------------------------------------


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
        severity = "error" if level == 2 else "warning"
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


# ---------------------------------------------------------------------------
# tsc (typecheck)
# ---------------------------------------------------------------------------


def _find_tsconfig(file_path: str) -> Path | None:
    """Walk up from file_path until a tsconfig.json is found."""
    current = Path(file_path).resolve().parent
    while True:
        candidate = current / TS_CONFIG_FILENAME
        if candidate.exists():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    return None


async def run_tsc(file_path: str, content: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run tsc --noEmit and return normalised Findings.

    Args:
        file_path: Absolute path to the TS file being verified.
        content: Unused — tsc reads from disk, not stdin.
        stage_name: Stage name to embed in each Finding (e.g. "typecheck").
        timeout: Seconds before the subprocess is killed.
    """
    tsconfig = _find_tsconfig(file_path)
    if tsconfig is None:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"No tsconfig.json found — skipping typecheck for {file_path}",
                code="tsc/no-tsconfig",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    try:
        proc = await asyncio.create_subprocess_exec(
            "tsc",
            "--noEmit",
            "--project",
            str(tsconfig),
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
                message="tsc not found — install with: npm install -D typescript",
                code="tsc/not-installed",
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
                message=f"tsc timed out after {timeout}s",
                code="tsc/timeout",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    await _cleanup(proc)

    if proc.returncode is None:
        return []

    if proc.returncode == 0:
        return []

    output = stdout.decode("utf-8", errors="replace")
    if proc.returncode != 1:
        snippet = output.strip()[:200]
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"tsc exited with code {proc.returncode} — stdout: {snippet}",
                code="tsc/error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    findings: list[Finding] = []
    for line in output.splitlines():
        match = _TSC_PATTERN.match(line.strip())
        if not match:
            continue
        severity = "error" if match.group(4) == "error" else "warning"
        findings.append(
            Finding(
                severity=severity,
                file=file_path,
                line=int(match.group(2)),
                column=int(match.group(3)),
                message=match.group(6),
                code=f"tsc/{match.group(5)}",
                stage=stage_name,
                fix_suggestion=None,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# Jest / Vitest (tests)
# ---------------------------------------------------------------------------


def _detect_js_runner(file_path: str) -> str | None:
    """Detect the JS test runner (jest/vitest) from the nearest package.json."""
    current = Path(file_path).resolve().parent
    while True:
        package_json = current / "package.json"
        if package_json.exists():
            try:
                parsed = json.loads(package_json.read_text())
            except json.JSONDecodeError:
                return None
            deps = {
                **parsed.get("dependencies", {}),
                **parsed.get("devDependencies", {}),
            }
            if "vitest" in deps:
                return "vitest"
            if "jest" in deps:
                return "jest"
            return None
        if current.parent == current:
            break
        current = current.parent
    return None


def _find_js_test_file(file_path: str) -> Path | None:
    """Return the test file for file_path, or None if none exists."""
    source = Path(file_path).resolve()
    stem = source.stem
    ext = source.suffix
    candidates = [
        source.with_name(f"{stem}.test{ext}"),
        source.with_name(f"{stem}.spec{ext}"),
        source.parent / "__tests__" / source.name,
    ]
    for path in candidates:
        if path.exists():
            return path
    return None


def _build_js_finding(
    file_path: str,
    runner: str,
    test_name: str,
    message: str,
    stage_name: str,
    line: int | None = None,
) -> Finding:
    """Build a single test-failure Finding."""
    return Finding(
        severity="error",
        file=file_path,
        line=line,
        column=None,
        message=f"{test_name}: {message}" if message else test_name,
        code=f"{runner}/assertion-failed",
        stage=stage_name,
        fix_suggestion=None,
    )


async def run_jest(
    file_path: str,
    stage_name: str,
    timeout: int,
    tool_override: str | None = None,
) -> list[Finding]:
    """Run Jest or Vitest against the test file paired with file_path.

    Args:
        file_path: Absolute path to the source file being verified.
        stage_name: Stage name to embed in each Finding (e.g. "tests").
        timeout: Seconds before the subprocess is killed.
        tool_override: Force a specific runner ("jest" or "vitest").
    """
    runner = (tool_override or "").lower() or _detect_js_runner(file_path)
    if runner not in {"jest", "vitest"}:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"No JS test runner detected (jest/vitest) — skipping tests for {file_path}",
                code="testsjs/no-runner",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    test_file = _find_js_test_file(file_path)
    if test_file is None:
        return []

    args = (
        ["jest", "--testPathPattern", str(test_file), "--json", "--no-coverage"]
        if runner == "jest"
        else ["vitest", "run", str(test_file), "--reporter", "json"]
    )

    try:
        proc = await asyncio.create_subprocess_exec(
            *args,
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
                message=f"{runner} not found — install via npm install -D {runner}",
                code=f"{runner}/not-installed",
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
                message=f"{runner} timed out after {timeout}s",
                code=f"{runner}/timeout",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    await _cleanup(proc)

    if proc.returncode is None or proc.returncode == 0:
        return []

    if proc.returncode >= 2:
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"{runner} exited with code {proc.returncode} — stderr: {stderr_text[:200]}",
                code=f"{runner}/error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    payload = stdout.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("[javascript] %s output not JSON: %s", runner, payload[:200])
        return []

    findings: list[Finding] = []
    if runner == "jest":
        test_results = parsed.get("testResults", [])
        for result in test_results:
            for assertion in result.get("assertionResults", []):
                if assertion.get("status") != "failed":
                    continue
                location = assertion.get("location") or {}
                msg = " ".join(assertion.get("failureMessages", []))
                findings.append(
                    _build_js_finding(
                        file_path,
                        runner,
                        assertion.get("fullName") or assertion.get("title", "test"),
                        msg,
                        stage_name,
                        location.get("line"),
                    )
                )
    else:
        test_results = parsed.get("tests") or parsed.get("testResults") or []
        for test in test_results:
            state = test.get("state") or test.get("status")
            if state not in {"fail", "failed"}:
                continue
            msg = ""
            errors = test.get("errors") or test.get("error")
            if isinstance(errors, list):
                msg = " ".join(str(e) for e in errors)
            elif isinstance(errors, dict):
                msg = errors.get("message", "")
            findings.append(
                _build_js_finding(
                    file_path,
                    runner,
                    test.get("name", "test"),
                    msg,
                    stage_name,
                    test.get("location", {}).get("line"),
                )
            )
    return findings
