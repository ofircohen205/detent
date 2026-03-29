# detent/stages/security/_secrets.py
"""Secret detection sub-stage using detect-secrets."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from detent.pipeline.result import Finding
from detent.stages._subprocess import cleanup_process

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


async def run_secret_scan(
    scan_path: str,
    original_path: str,
    stage_name: str,
    timeout: int,
) -> list[Finding]:
    """Scan a file for hardcoded secrets using detect-secrets.

    Args:
        scan_path: Path to the (temporary) file to scan.
        original_path: Original file path used for Finding attribution and
            display -- must not be the temp path.
        stage_name: Stage name string used for Finding attribution.
        timeout: Subprocess timeout in seconds.

    Returns:
        List of Findings.  Empty list means no secrets detected.
    """
    logger.debug("secret_scan.start", file=original_path)
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
                message="detect-secrets not found -- install with: pip install detect-secrets",
                code="secrets/not-installed",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    try:
        try:
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        except TimeoutError:
            await cleanup_process(proc)
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
    finally:
        await cleanup_process(proc)

    if proc.returncode != 0:
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        return [
            Finding(
                severity="warning",
                file=original_path,
                line=None,
                column=None,
                message=f"detect-secrets exited with code {proc.returncode} -- stderr: {stderr_text[:200]}",
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
    logger.debug("secret_scan.complete", file=original_path, findings=len(findings))
    return findings
