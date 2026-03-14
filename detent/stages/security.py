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

"""SecurityStage — Semgrep + Bandit static analysis."""

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

from detent.config import StageConfig
from detent.pipeline.result import Finding, VerificationResult
from detent.stages.base import VerificationStage, _validate_file_path

if TYPE_CHECKING:
    from detent.schema import AgentAction

logger = logging.getLogger(__name__)

_SEMGREP_SEVERITY_MAP: dict[str, Literal["error", "warning", "info"]] = {
    "ERROR": "error",
    "WARNING": "warning",
    "INFO": "warning",
}
_BANDIT_SEVERITY_MAP: dict[str, Literal["error", "warning", "info"]] = {
    "HIGH": "error",
    "MEDIUM": "warning",
    "LOW": "warning",
}


class SecurityStage(VerificationStage):
    """Run Semgrep and Bandit as a combined security stage."""

    name = "security"

    def __init__(self, config: StageConfig | None = None) -> None:
        super().__init__(config)
        if config is None:
            config = StageConfig(name=self.name)
        semgrep_opts = config.options.get("semgrep", {})
        bandit_opts = config.options.get("bandit", {})
        self._semgrep_enabled: bool = semgrep_opts.get("enabled", True)
        self._semgrep_rulesets: list[str] = semgrep_opts.get(
            "rulesets",
            ["p/python", "p/owasp-top-ten"],
        )
        self._bandit_enabled: bool = bandit_opts.get("enabled", True)
        self._bandit_confidence: str = bandit_opts.get("confidence", "low")
        self._timeout: int = config.timeout

    def supports_language(self, lang: str) -> bool:
        """Semgrep supports multiple languages; Bandit is handled internally."""
        return True

    async def _run(self, action: AgentAction) -> VerificationResult:
        """Run Semgrep and Bandit concurrently on the proposed content."""
        start = time.perf_counter()

        file_path = action.file_path or ""
        content = action.content or ""

        if file_path:
            _validate_file_path(file_path)
        if not file_path:
            duration_ms = (time.perf_counter() - start) * 1000
            return VerificationResult(
                stage=self.name,
                passed=True,
                findings=[],
                duration_ms=duration_ms,
                metadata={"skipped": True, "reason": "No file_path in action"},
            )

        if not self._semgrep_enabled and not self._bandit_enabled:
            duration_ms = (time.perf_counter() - start) * 1000
            return VerificationResult(
                stage=self.name,
                passed=True,
                findings=[],
                duration_ms=duration_ms,
                metadata={"skipped": True, "reason": "Both tools disabled"},
            )

        suffix = Path(file_path).suffix or ".txt"
        tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
        try:
            with os.fdopen(tmp_fd, "w") as f:
                f.write(content)
            tmp_fd = -1

            tasks: list[asyncio.Task[list[Finding]]] = []
            if self._semgrep_enabled:
                tasks.append(asyncio.create_task(self._run_semgrep(tmp_path, file_path)))
            if self._bandit_enabled and Path(file_path).suffix.lower() == ".py":
                tasks.append(asyncio.create_task(self._run_bandit(tmp_path, file_path)))

            if not tasks:
                duration_ms = (time.perf_counter() - start) * 1000
                return VerificationResult(
                    stage=self.name,
                    passed=True,
                    findings=[],
                    duration_ms=duration_ms,
                    metadata={"skipped": True, "reason": "No applicable tools"},
                )

            results = await asyncio.gather(*tasks, return_exceptions=True)
            findings: list[Finding] = []
            for result in results:
                if isinstance(result, BaseException):
                    findings.append(
                        Finding(
                            severity="warning",
                            file=file_path,
                            line=None,
                            column=None,
                            message=f"Security tool failed unexpectedly: {result}",
                            code="security/error",
                            stage=self.name,
                            fix_suggestion=None,
                        )
                    )
                else:
                    findings.extend(result)

        finally:
            if tmp_fd != -1:
                with contextlib.suppress(OSError):
                    os.close(tmp_fd)
            with contextlib.suppress(OSError):
                os.unlink(tmp_path)

        findings = self._dedupe_findings(findings)
        passed = not any(f.severity == "error" for f in findings)
        duration_ms = (time.perf_counter() - start) * 1000

        return VerificationResult(
            stage=self.name,
            passed=passed,
            findings=findings,
            duration_ms=duration_ms,
            metadata={"tools": ["semgrep", "bandit"]},
        )

    async def _run_semgrep(self, scan_path: str, original_path: str) -> list[Finding]:
        """Run semgrep and parse JSON output."""
        args = [
            "semgrep",
            "scan",
            "--json",
            "--timeout",
            str(self._timeout),
        ]
        for ruleset in self._semgrep_rulesets:
            args.extend(["--config", ruleset])
        args.append(scan_path)

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
                    file=original_path,
                    line=None,
                    column=None,
                    message="semgrep not found — install with: pip install semgrep",
                    code="semgrep/not-installed",
                    stage=self.name,
                    fix_suggestion=None,
                )
            ]

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except TimeoutError:
            return [
                Finding(
                    severity="warning",
                    file=original_path,
                    line=None,
                    column=None,
                    message=f"semgrep timed out after {self._timeout}s",
                    code="semgrep/timeout",
                    stage=self.name,
                    fix_suggestion=None,
                )
            ]
        finally:
            await self._cleanup_process(proc)

        if proc.returncode == 0:
            return []

        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode != 1:
            return [
                Finding(
                    severity="warning",
                    file=original_path,
                    line=None,
                    column=None,
                    message=f"semgrep exited with code {proc.returncode} — stderr: {stderr_text[:200]}",
                    code="semgrep/error",
                    stage=self.name,
                    fix_suggestion=None,
                )
            ]

        raw_output = stdout.decode("utf-8", errors="replace").strip()
        try:
            parsed: dict[str, Any] = json.loads(raw_output) if raw_output else {}
        except json.JSONDecodeError:
            return [
                Finding(
                    severity="warning",
                    file=original_path,
                    line=None,
                    column=None,
                    message="semgrep output was not valid JSON",
                    code="semgrep/error",
                    stage=self.name,
                    fix_suggestion=None,
                )
            ]

        for error in parsed.get("errors", []):
            logger.warning("[security] semgrep error: %s", error)

        findings: list[Finding] = []
        for result in parsed.get("results", []):
            findings.append(self._parse_semgrep_result(result, original_path))
        return findings

    async def _run_bandit(self, scan_path: str, original_path: str) -> list[Finding]:
        """Run bandit and parse JSON output."""
        args = ["bandit", "-f", "json"]
        if self._bandit_confidence == "medium":
            args.append("-i")
        elif self._bandit_confidence == "high":
            args.append("-ii")
        args.append(scan_path)

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
                    file=original_path,
                    line=None,
                    column=None,
                    message="bandit not found — install with: pip install bandit",
                    code="bandit/not-installed",
                    stage=self.name,
                    fix_suggestion=None,
                )
            ]

        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=self._timeout)
        except TimeoutError:
            return [
                Finding(
                    severity="warning",
                    file=original_path,
                    line=None,
                    column=None,
                    message=f"bandit timed out after {self._timeout}s",
                    code="bandit/timeout",
                    stage=self.name,
                    fix_suggestion=None,
                )
            ]
        finally:
            await self._cleanup_process(proc)

        if proc.returncode == 0:
            return []

        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        if proc.returncode != 1:
            return [
                Finding(
                    severity="warning",
                    file=original_path,
                    line=None,
                    column=None,
                    message=f"bandit exited with code {proc.returncode} — stderr: {stderr_text[:200]}",
                    code="bandit/error",
                    stage=self.name,
                    fix_suggestion=None,
                )
            ]

        raw_output = stdout.decode("utf-8", errors="replace").strip()
        try:
            parsed: dict[str, Any] = json.loads(raw_output) if raw_output else {}
        except json.JSONDecodeError:
            return [
                Finding(
                    severity="warning",
                    file=original_path,
                    line=None,
                    column=None,
                    message="bandit output was not valid JSON",
                    code="bandit/error",
                    stage=self.name,
                    fix_suggestion=None,
                )
            ]

        findings: list[Finding] = []
        for result in parsed.get("results", []):
            findings.append(self._parse_bandit_result(result, original_path))
        return findings

    def _parse_semgrep_result(self, raw: dict[str, Any], original_path: str) -> Finding:
        severity = _SEMGREP_SEVERITY_MAP.get(raw.get("extra", {}).get("severity", "ERROR"), "error")
        start = raw.get("start", {})
        extra = raw.get("extra", {})
        return Finding(
            severity=severity,
            file=original_path,
            line=start.get("line"),
            column=start.get("col"),
            message=extra.get("message", ""),
            code=f"semgrep/{raw.get('check_id', 'unknown')}",
            stage=self.name,
            fix_suggestion=extra.get("fix"),
        )

    def _parse_bandit_result(self, raw: dict[str, Any], original_path: str) -> Finding:
        severity = _BANDIT_SEVERITY_MAP.get(raw.get("issue_severity", "MEDIUM"), "warning")
        return Finding(
            severity=severity,
            file=original_path,
            line=raw.get("line_number"),
            column=None,
            message=raw.get("issue_text", ""),
            code=f"bandit/{raw.get('test_id', 'unknown')}",
            stage=self.name,
            fix_suggestion=None,
        )

    async def _cleanup_process(self, proc: asyncio.subprocess.Process) -> None:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(Exception):
                await proc.communicate()

    def _dedupe_findings(self, findings: list[Finding]) -> list[Finding]:
        seen: set[tuple[str, int | None, str]] = set()
        deduped: list[Finding] = []
        for finding in findings:
            key = (finding.file, finding.line, finding.message)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(finding)
        return deduped
