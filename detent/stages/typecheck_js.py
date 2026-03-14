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

"""TypeScript typechecker (tsc) integration used by TypecheckStage."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import re
from pathlib import Path

from detent.pipeline.result import Finding

logger = logging.getLogger(__name__)

_TSC_PATTERN = re.compile(r"^(.+)\((\d+),(\d+)\): (error|warning) (TS\d+): (.+)$")


def _find_tsconfig(file_path: str) -> Path | None:
    current = Path(file_path).resolve().parent
    while True:
        candidate = current / "tsconfig.json"
        if candidate.exists():
            return candidate
        if current.parent == current:
            break
        current = current.parent
    return None


async def run_tsc(file_path: str, timeout: int) -> list[Finding]:
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
                stage="typecheck",
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
                stage="typecheck",
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
                message=f"tsc timed out after {timeout}s",
                code="tsc/timeout",
                stage="typecheck",
                fix_suggestion=None,
            )
        ]

    await _cleanup_process(proc)

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
                stage="typecheck",
                fix_suggestion=None,
            )
        ]

    findings = []
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
                stage="typecheck",
                fix_suggestion=None,
            )
        )
    return findings


async def _cleanup_process(proc: asyncio.subprocess.Process) -> None:
    if proc.returncode is None:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.communicate()
