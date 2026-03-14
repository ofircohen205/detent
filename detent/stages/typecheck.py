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

"""TypecheckStage — mypy type checking via temp file.

mypy does not support stdin, so we write content to a temp file,
run mypy on it, then delete the temp file. The temp file path is
remapped back to action.file_path in all findings.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from detent.schema import AgentAction

from detent.pipeline.result import Finding, VerificationResult
from detent.stages.base import VerificationStage, _validate_file_path
from detent.stages.typecheck_js import run_tsc

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = frozenset({".py"})
_TS_EXTENSIONS = frozenset({".ts", ".tsx"})
_SEVERITY_MAP: dict[str, Literal["error", "warning", "info"]] = {
    "error": "error",
    "warning": "warning",
    "note": "info",
}


class TypecheckStage(VerificationStage):
    """Type-checks proposed file content using mypy.

    Writes content to a temp file, runs mypy with --output=json, parses
    results, then deletes the temp file. The temp file path is remapped
    to action.file_path in all reported findings.
    """

    name = "typecheck"

    def supports_language(self, lang: str) -> bool:
        """Return True only for Python."""
        return lang in {"python", "py", "typescript"}

    async def _run(self, action: AgentAction) -> VerificationResult:
        """Type-check content using mypy via temp file."""
        start = time.perf_counter()

        file_path = action.file_path or ""
        content = action.content or ""

        if file_path:
            _validate_file_path(file_path)

        ext = Path(file_path).suffix.lower()
        if ext in _TS_EXTENSIONS:
            findings = await run_tsc(
                file_path,
                self._config.timeout if self._config else 30,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            return VerificationResult(
                stage=self.name,
                passed=len(findings) == 0,
                findings=findings,
                duration_ms=duration_ms,
                metadata={"tool": "tsc"},
            )

        if ext not in _SUPPORTED_EXTENSIONS:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.debug("[typecheck] skipping unsupported extension: %s", ext)
            return VerificationResult(
                stage=self.name,
                passed=True,
                findings=[],
                duration_ms=duration_ms,
                metadata={"skipped": True, "reason": f"Unsupported extension: {ext}"},
            )

        returncode: int | None = None
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=".py")
        try:
            with os.fdopen(tmp_fd, "w") as f:
                f.write(content)
            tmp_fd = -1  # fd is now owned by the file object; don't close again

            logger.debug("[typecheck] running mypy on %s (temp: %s)", file_path, tmp_path)

            proc = await asyncio.create_subprocess_exec(
                "mypy",
                "--output=json",
                "--no-error-summary",
                "--ignore-missing-imports",
                tmp_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            returncode = proc.returncode

        finally:
            if tmp_fd != -1:
                with contextlib.suppress(OSError):
                    os.close(tmp_fd)  # only if fdopen never took ownership
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

        duration_ms = (time.perf_counter() - start) * 1000
        raw_output = stdout.decode("utf-8", errors="replace").strip()

        findings: list[Finding] = []
        for line in raw_output.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                raw: dict[str, Any] = json.loads(line)
                findings.append(self._parse_finding(raw, file_path))
            except json.JSONDecodeError:
                logger.debug("[typecheck] non-JSON mypy output: %s", line)

        # Filter out "info" (mypy "note" severity) -- contextual hints, not type errors
        findings = [f for f in findings if f.severity != "info"]

        return VerificationResult(
            stage=self.name,
            passed=len(findings) == 0,
            findings=findings,
            duration_ms=duration_ms,
            metadata={"returncode": returncode},
        )

    def _parse_finding(self, raw: dict[str, Any], original_path: str) -> Finding:
        """Convert a single mypy JSON finding to a Finding object.

        Always uses original_path as the file (temp file path is discarded).
        mypy col is 0-indexed; we keep as-is since Finding has no convention.
        mypy severity: "error", "warning", "note" (mapped to "info" and then filtered).
        """
        severity = _SEVERITY_MAP.get(raw.get("severity", "error"), "error")
        return Finding(
            severity=severity,
            file=original_path,
            line=raw.get("line"),
            column=raw.get("col"),
            message=raw.get("message", ""),
            code=raw.get("code"),
            stage=self.name,
            fix_suggestion=None,
        )
