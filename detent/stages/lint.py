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
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from detent.schema import AgentAction

from detent.pipeline.result import Finding, VerificationResult
from detent.stages.base import VerificationStage

logger = logging.getLogger(__name__)

_SUPPORTED_EXTENSIONS = frozenset({".py"})


class LintStage(VerificationStage):
    """Lints proposed file content using Ruff.

    Content is piped via stdin — no temp file is written. Ruff exit codes:
    0 = clean, 1 = violations found, 2 = ruff internal error.
    """

    name = "lint"

    def supports_language(self, lang: str) -> bool:
        """Return True only for Python."""
        return lang in {"python", "py"}

    async def _run(self, action: AgentAction) -> VerificationResult:
        """Lint content using ruff check via stdin."""
        start = time.perf_counter()

        file_path = action.file_path or ""
        content = action.content or ""

        ext = Path(file_path).suffix.lower()
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
        raw_findings: list[dict[str, Any]] = json.loads(raw_output) if raw_output else []
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
        return Finding(
            severity="error",
            file=raw.get("filename", ""),
            line=location.get("row"),
            column=location.get("column"),
            message=raw.get("message", ""),
            code=raw.get("code"),
            stage=self.name,
            fix_suggestion=None,
        )
