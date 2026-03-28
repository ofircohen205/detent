# detent/stages/security/_dep_scan.py
"""Dependency vulnerability scanning sub-stage using pip-audit."""

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


def is_dependency_manifest(file_path: str) -> bool:
    """Return True if file_path is a Python requirements manifest that pip-audit can scan.

    Matches ``requirements.txt`` and any file whose name starts with
    ``requirements`` and ends with ``.txt`` (e.g. ``requirements-dev.txt``).
    """
    name = Path(file_path).name
    return name == "requirements.txt" or (name.startswith("requirements") and name.endswith(".txt"))


async def run_dep_scan(
    content: str,
    file_path: str,
    stage_name: str,
    timeout: int,
) -> list[Finding]:
    """Scan a proposed requirements file for known vulnerabilities using pip-audit.

    Returns an empty list when ``file_path`` is not a recognised dependency
    manifest.  Returns one Finding (severity "error") per vulnerable package,
    or a warning Finding if pip-audit is not installed or fails unexpectedly.

    Args:
        content: The proposed requirements file content.
        file_path: Original file path -- used in Finding.file and to determine
            whether this is a manifest that should be scanned.
        stage_name: Stage name string used for Finding attribution.
        timeout: Subprocess timeout in seconds.

    Returns:
        List of Findings. Empty list means no vulnerabilities detected.
    """
    if not is_dependency_manifest(file_path):
        return []

    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".txt")
    try:
        with os.fdopen(tmp_fd, "w") as fh:
            fh.write(content)
        tmp_fd = -1
        return await _run_pip_audit(tmp_path, file_path, stage_name, timeout)
    finally:
        if tmp_fd != -1:
            with contextlib.suppress(OSError):
                os.close(tmp_fd)
        with contextlib.suppress(OSError):
            os.unlink(tmp_path)


async def _run_pip_audit(
    req_path: str,
    original_path: str,
    stage_name: str,
    timeout: int,
) -> list[Finding]:
    """Invoke pip-audit against req_path and return parsed Findings."""
    logger.debug("dep_scan.start", file=original_path)
    try:
        proc = await asyncio.create_subprocess_exec(
            "pip-audit",
            "-r",
            req_path,
            "--format",
            "json",
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
                message="pip-audit not found -- install with: pip install pip-audit",
                code="dep-scan/not-installed",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    try:
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
                    message=f"pip-audit timed out after {timeout}s",
                    code="dep-scan/timeout",
                    stage=stage_name,
                    fix_suggestion=None,
                )
            ]
    finally:
        if proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                proc.kill()
            with contextlib.suppress(Exception):
                await proc.communicate()

    # exit 0 = no vulns; exit 1 = vulns found; anything else = error
    if proc.returncode not in (0, 1):
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        return [
            Finding(
                severity="warning",
                file=original_path,
                line=None,
                column=None,
                message=f"pip-audit exited with code {proc.returncode} -- stderr: {stderr_text[:200]}",
                code="dep-scan/error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    raw = stdout.decode("utf-8", errors="replace").strip()
    if not raw:
        return []
    try:
        parsed: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError:
        return [
            Finding(
                severity="warning",
                file=original_path,
                line=None,
                column=None,
                message="pip-audit output was not valid JSON",
                code="dep-scan/error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]

    findings: list[Finding] = []
    for pkg in parsed.get("dependencies", []):
        for vuln in pkg.get("vulns", []):
            fix_versions: list[str] = vuln.get("fix_versions", [])
            fix = (
                f"Upgrade to {fix_versions[0]}"
                if fix_versions
                else "No fix available; consider removing or replacing this dependency."
            )
            findings.append(
                Finding(
                    severity="error",
                    file=original_path,
                    line=None,
                    column=None,
                    message=f"{pkg['name']}=={pkg['version']}: {vuln.get('description', vuln['id'])}",
                    code=f"dep-scan/{vuln['id']}",
                    stage=stage_name,
                    fix_suggestion=fix,
                )
            )

    logger.debug("dep_scan.complete", file=original_path, findings=len(findings))
    return findings
