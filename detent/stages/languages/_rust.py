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

"""Shared Rust helpers used by lint, typecheck, and tests stages."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
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
