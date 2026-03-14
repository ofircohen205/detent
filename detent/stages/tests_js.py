# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Detent Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""JS/TS test runner (Jest/Vitest) used by TestsStage."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path

from detent.pipeline.result import Finding

logger = logging.getLogger(__name__)


def _detect_js_runner(file_path: str) -> str | None:
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


def _find_test_file(file_path: str) -> Path | None:
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


def _build_finding(
    file_path: str,
    runner: str,
    test_name: str,
    message: str,
    line: int | None = None,
) -> Finding:
    return Finding(
        severity="error",
        file=file_path,
        line=line,
        column=None,
        message=f"{test_name}: {message}" if message else test_name,
        code=f"{runner}/assertion-failed",
        stage="tests",
        fix_suggestion=None,
    )


async def run_js_tests(
    file_path: str,
    timeout: int,
    tool_override: str | None,
) -> list[Finding]:
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
                stage="tests",
                fix_suggestion=None,
            )
        ]

    test_file = _find_test_file(file_path)
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
                stage="tests",
                fix_suggestion=None,
            )
        ]

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        await _cleanup_process(proc)
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"{runner} timed out after {timeout}s",
                code=f"{runner}/timeout",
                stage="tests",
                fix_suggestion=None,
            )
        ]

    await _cleanup_process(proc)

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
                stage="tests",
                fix_suggestion=None,
            )
        ]

    payload = stdout.decode("utf-8", errors="replace")
    try:
        parsed = json.loads(payload)
    except json.JSONDecodeError:
        logger.warning("[tests_js] %s output not JSON: %s", runner, payload[:200])
        return []

    findings: list[Finding] = []
    if runner == "jest":
        test_results = parsed.get("testResults", [])
        for result in test_results:
            for assertion in result.get("assertionResults", []):
                if assertion.get("status") != "failed":
                    continue
                location = assertion.get("location") or {}
                message = " ".join(assertion.get("failureMessages", []))
                findings.append(
                    _build_finding(
                        file_path,
                        runner,
                        assertion.get("fullName") or assertion.get("title", "test"),
                        message,
                        location.get("line"),
                    )
                )
    else:
        test_results = parsed.get("tests") or parsed.get("testResults") or []
        for test in test_results:
            state = test.get("state") or test.get("status")
            if state not in {"fail", "failed"}:
                continue
            message = ""
            errors = test.get("errors") or test.get("error")
            if isinstance(errors, list):
                message = " ".join(str(e) for e in errors)
            elif isinstance(errors, dict):
                message = errors.get("message", "")
            findings.append(
                _build_finding(
                    file_path,
                    runner,
                    test.get("name", "test"),
                    message,
                    test.get("location", {}).get("line"),
                )
            )
    return findings


async def _cleanup_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.communicate()
