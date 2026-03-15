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

"""Rust verification helpers: cargo clippy, cargo check, cargo test."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from detent.pipeline.result import Finding

logger = logging.getLogger(__name__)


def find_crate_root(file_path: str) -> tuple[Path, str] | None:
    """Walk up to find Cargo.toml; return (root, crate_name) or None.

    Handles workspace Cargo.toml by finding the member containing file_path.
    """
    current = Path(file_path).resolve().parent
    while True:
        cargo_toml = current / "Cargo.toml"
        if cargo_toml.exists():
            try:
                data = tomllib.loads(cargo_toml.read_text(encoding="utf-8"))
            except Exception:
                return None
            if "package" in data:
                return current, data["package"]["name"]
            if "workspace" in data:
                file_resolved = Path(file_path).resolve()
                for pattern in data["workspace"].get("members", []):
                    for member_dir in current.glob(pattern):
                        if not (member_dir / "Cargo.toml").exists():
                            continue
                        try:
                            file_resolved.relative_to(member_dir)
                        except ValueError:
                            continue
                        try:
                            md = tomllib.loads((member_dir / "Cargo.toml").read_text(encoding="utf-8"))
                            return current, md["package"]["name"]
                        except Exception:
                            return None
                return None
        if current.parent == current:
            return None
        current = current.parent


def _not_found_finding(file_path: str, stage_name: str) -> Finding:
    """Return a Finding indicating cargo is not installed."""
    return Finding(
        severity="warning",
        file=file_path,
        line=None,
        column=None,
        message="cargo not found — install from https://rustup.rs",
        code="cargo/not-installed",
        stage=stage_name,
        fix_suggestion=None,
    )


def _no_cargo_finding(file_path: str, stage_name: str) -> Finding:
    """Return a Finding indicating no Cargo.toml was found."""
    return Finding(
        severity="warning",
        file=file_path,
        line=None,
        column=None,
        message="no Cargo.toml found — is this a Rust crate?",
        code="cargo/no-manifest",
        stage=stage_name,
        fix_suggestion=None,
    )


def _parse_cargo_json(stdout: bytes, file_path: str, stage_name: str) -> list[Finding]:
    """Parse cargo --message-format=json; process only reason=compiler-message."""
    findings: list[Finding] = []
    for raw_line in stdout.decode("utf-8", errors="replace").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            logger.debug("[%s] cargo: malformed JSON: %s", stage_name, raw_line)
            continue
        if obj.get("reason") != "compiler-message":
            continue
        msg = obj.get("message", {})
        level = msg.get("level", "")
        if level in ("note", "help"):
            continue
        severity = "error" if level == "error" else "warning"
        line: int | None = None
        col: int | None = None
        for span in msg.get("spans", []):
            if span.get("is_primary"):
                line = span.get("line_start")
                col = span.get("column_start")
                break
        code_obj = msg.get("code") or {}
        findings.append(
            Finding(
                severity=severity,  # type: ignore[arg-type]
                file=file_path,
                line=line,
                column=col,
                message=msg.get("message", ""),
                code=f"cargo/{code_obj.get('code', 'unknown')}",
                stage=stage_name,
                fix_suggestion=None,
            )
        )
    return findings


async def _run_cargo(cmd: list[str], crate_root: Path, timeout: int) -> tuple[bytes, bytes, int | None]:
    """Run a cargo command in crate_root; return (stdout, stderr, returncode)."""
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(crate_root),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.communicate()
        raise
    return stdout, stderr, proc.returncode


async def run_clippy(file_path: str, content: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run cargo clippy --message-format=json and return findings."""
    info = find_crate_root(file_path)
    if info is None:
        return [_no_cargo_finding(file_path, stage_name)]
    crate_root, crate_name = info
    Path(file_path).write_text(content, encoding="utf-8")
    logger.debug("[%s] cargo clippy -p %s (cwd=%s)", stage_name, crate_name, crate_root)
    try:
        stdout, stderr, rc = await _run_cargo(
            ["cargo", "clippy", "--message-format=json", "-p", crate_name],
            crate_root,
            timeout,
        )
    except FileNotFoundError:
        return [_not_found_finding(file_path, stage_name)]
    except TimeoutError:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"cargo clippy timed out after {timeout}s",
                code="cargo/timeout",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]
    logger.debug("[%s] cargo clippy returncode=%s", stage_name, rc)
    if rc == 0:
        return []
    if rc is not None and rc >= 101:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"cargo clippy error: {stderr.decode('utf-8', errors='replace').strip()[:200]}",
                code="cargo/clippy-error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]
    return _parse_cargo_json(stdout, file_path, stage_name)


async def run_check(file_path: str, content: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run cargo check --message-format=json and return findings."""
    info = find_crate_root(file_path)
    if info is None:
        return [_no_cargo_finding(file_path, stage_name)]
    crate_root, crate_name = info
    Path(file_path).write_text(content, encoding="utf-8")
    logger.debug("[%s] cargo check -p %s (cwd=%s)", stage_name, crate_name, crate_root)
    try:
        stdout, stderr, rc = await _run_cargo(
            ["cargo", "check", "--message-format=json", "-p", crate_name],
            crate_root,
            timeout,
        )
    except FileNotFoundError:
        return [_not_found_finding(file_path, stage_name)]
    except TimeoutError:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"cargo check timed out after {timeout}s",
                code="cargo/timeout",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]
    logger.debug("[%s] cargo check returncode=%s", stage_name, rc)
    if rc == 0:
        return []
    if rc is not None and rc >= 101:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"cargo check error: {stderr.decode('utf-8', errors='replace').strip()[:200]}",
                code="cargo/check-error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]
    return _parse_cargo_json(stdout, file_path, stage_name)


_FAIL_RE = re.compile(r"^test\s+(\S+)\s+\.\.\.\s+FAILED$")


async def run_test(file_path: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run cargo test -p <crate> and return findings for failed tests."""
    info = find_crate_root(file_path)
    if info is None:
        return [_no_cargo_finding(file_path, stage_name)]
    crate_root, crate_name = info
    logger.debug("[%s] cargo test -p %s (cwd=%s)", stage_name, crate_name, crate_root)
    try:
        stdout, stderr, rc = await _run_cargo(
            ["cargo", "test", "-p", crate_name],
            crate_root,
            timeout,
        )
    except FileNotFoundError:
        return [_not_found_finding(file_path, stage_name)]
    except TimeoutError:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"cargo test timed out after {timeout}s",
                code="cargo/timeout",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]
    logger.debug("[%s] cargo test returncode=%s", stage_name, rc)
    if rc == 101:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"cargo test binary compile error: {stderr.decode('utf-8', errors='replace').strip()[:200]}",
                code="cargo/test-compile-error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]
    if rc == 0:
        return []
    return _parse_cargo_test_output(stdout.decode("utf-8", errors="replace"), file_path, stage_name)


def _parse_cargo_test_output(output: str, file_path: str, stage_name: str) -> list[Finding]:
    """Parse cargo test stdout for FAILED test lines."""
    findings = []
    for line in output.splitlines():
        if "running 0 tests" in line:
            return []
        m = _FAIL_RE.match(line.strip())
        if m:
            findings.append(
                Finding(
                    severity="error",
                    file=file_path,
                    line=None,
                    column=None,
                    message=f"Test failed: {m.group(1)}",
                    code="cargo/test-failed",
                    stage=stage_name,
                    fix_suggestion=None,
                )
            )
    return findings
