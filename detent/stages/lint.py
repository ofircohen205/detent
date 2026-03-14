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

"""LintStage — Ruff linting via stdin.

Uses `ruff check --output-format json --stdin-filename <path> -` so no temp file
is written. Ruff uses the --stdin-filename value for all path references in output.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from detent.schema import AgentAction

from detent.config.languages import JS_TS_EXTENSIONS, PYTHON_EXTENSIONS
from detent.pipeline.result import Finding, VerificationResult
from detent.stages.base import VerificationStage, _validate_file_path
from detent.stages.lint_js import run_eslint

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = PYTHON_EXTENSIONS
_JS_EXTENSIONS = JS_TS_EXTENSIONS


class LintStage(VerificationStage):
    """Lints proposed file content using Ruff.

    Content is piped via stdin — no temp file is written. Ruff exit codes:
    0 = clean, 1 = violations found, 2 = ruff internal error.
    """

    name = "lint"

    def supports_language(self, lang: str) -> bool:
        """Return True only for Python."""
        return lang in {"python", "javascript", "typescript"}

    async def _run(self, action: AgentAction) -> VerificationResult:
        """Lint content using ruff check via stdin."""
        start = time.perf_counter()

        file_path = action.file_path or ""
        content = action.content or ""

        if file_path:
            _validate_file_path(file_path)

        ext = Path(file_path).suffix.lower()
        if ext in _JS_EXTENSIONS:
            findings = await run_eslint(
                file_path,
                content,
                self._config.timeout if self._config else 30,
            )
            duration_ms = (time.perf_counter() - start) * 1000
            return VerificationResult(
                stage=self.name,
                passed=len(findings) == 0,
                findings=findings,
                duration_ms=duration_ms,
                metadata={"tool": "eslint"},
            )

        if ext not in _SUPPORTED_EXTENSIONS:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.debug("[lint] skipping unsupported extension: %s", ext)
            return VerificationResult(
                stage=self.name,
                passed=True,
                findings=[],
                duration_ms=duration_ms,
                metadata={"skipped": True, "reason": f"Unsupported extension: {ext}"},
            )

        logger.debug("[lint] running ruff on %s (%d bytes)", file_path, len(content))

        proc = await asyncio.create_subprocess_exec(
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
        )
        stdout, stderr = await proc.communicate(input=content.encode("utf-8"))

        duration_ms = (time.perf_counter() - start) * 1000

        if proc.returncode == 2:
            error_msg = stderr.decode("utf-8", errors="replace").strip()
            logger.error("[lint] ruff error: %s", error_msg)
            return VerificationResult(
                stage=self.name,
                passed=False,
                findings=[
                    Finding(
                        severity="error",
                        file=file_path,
                        line=None,
                        column=None,
                        message=f"Ruff failed: {error_msg}",
                        code="ruff-internal-error",
                        stage=self.name,
                        fix_suggestion=None,
                    )
                ],
                duration_ms=duration_ms,
                metadata={"returncode": proc.returncode},
            )

        raw_output = stdout.decode("utf-8", errors="replace").strip()
        try:
            raw_findings: list[dict[str, Any]] = json.loads(raw_output) if raw_output else []
        except json.JSONDecodeError:
            logger.warning("[lint] ruff output was not valid JSON: %s", raw_output[:200])
            raw_findings = []
        findings = [self._parse_finding(f) for f in raw_findings]

        return VerificationResult(
            stage=self.name,
            passed=len(findings) == 0,
            findings=findings,
            duration_ms=duration_ms,
            metadata={"returncode": proc.returncode},
        )

    def _parse_finding(self, raw: dict[str, Any]) -> Finding:
        """Convert a single Ruff JSON finding to a Finding object."""
        location = raw.get("location", {})
        code = raw.get("code") or ""
        # Map Ruff code prefix to Finding severity:
        # W = pycodestyle warnings, I = isort (informational)
        # Everything else (E, F, B, N, A, SIM, UP, TCH...) = error
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
            stage=self.name,
            fix_suggestion=None,
        )
