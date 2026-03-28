# detent/stages/security/_secrets.py
"""Secret detection sub-stage using detect-secrets."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any

import structlog

from detent.pipeline.result import Finding

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


async def run_secret_scan(
    content: str,
    file_path: str,
    stage_name: str,
    timeout: int,
) -> list[Finding]:
    """Scan proposed file content for hardcoded secrets using detect-secrets.

    Writes content to a temporary file, invokes ``detect-secrets scan``, and
    returns one Finding (severity "error") per detected secret.  Returns a
    warning Finding if detect-secrets is not installed or fails unexpectedly.

    Args:
        content: The proposed file content to scan.
        file_path: Original file path (used in Finding.file and for the suffix
            of the temp file so detect-secrets can infer file type).
        stage_name: Stage name string used for Finding attribution.
        timeout: Subprocess timeout in seconds.

    Returns:
        List of Findings. Empty list means no secrets detected.
    """
    suffix = Path(file_path).suffix or ".txt"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    try:
        with os.fdopen(tmp_fd, "w") as fh:
            fh.write(content)
        tmp_fd = -1
        return await _scan_file(tmp_path, file_path, stage_name, timeout)
    finally:
        if tmp_fd != -1:
            with contextlib.suppress(OSError):
                os.close(tmp_fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


async def _scan_file(
    scan_path: str,
    original_path: str,
    stage_name: str,
    timeout: int,
) -> list[Finding]:
    """Invoke detect-secrets on scan_path and return parsed Findings."""
    try:
        proc = await asyncio.create_subprocess_exec(
            "detect-secrets",
            "scan",
            scan_path,
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
                message="detect-secrets not found — install with: pip install detect-secrets",
                code="secrets/not-installed",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        with contextlib.suppress(Exception):
            await proc.communicate()
        return [
            Finding(
                severity="warning",
                file=original_path,
                line=None,
                column=None,
                message=f"detect-secrets timed out after {timeout}s",
                code="secrets/timeout",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    if proc.returncode != 0:
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        return [
            Finding(
                severity="warning",
                file=original_path,
                line=None,
                column=None,
                message=f"detect-secrets exited with code {proc.returncode} — stderr: {stderr_text[:200]}",
                code="secrets/error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    raw = stdout.decode("utf-8", errors="replace").strip()
    try:
        parsed: dict[str, Any] = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        return [
            Finding(
                severity="warning",
                file=original_path,
                line=None,
                column=None,
                message="detect-secrets output was not valid JSON",
                code="secrets/error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    findings: list[Finding] = []
    for _filename, hits in parsed.get("results", {}).items():
        for hit in hits:
            secret_type: str = hit.get("type", "unknown")
            findings.append(
                Finding(
                    severity="error",
                    file=original_path,
                    line=hit.get("line_number"),
                    column=None,
                    message=f"Hardcoded secret detected: {secret_type}",
                    code=f"secrets/{secret_type.lower().replace(' ', '-')}",
                    stage=stage_name,
                    fix_suggestion=(
                        "Remove the hardcoded secret and use an environment variable " "or secrets manager instead."
                    ),
                )
            )
    return findings
