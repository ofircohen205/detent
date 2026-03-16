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

"""Shared Go helpers used by lint, typecheck, and tests stages."""

from __future__ import annotations

import re
from pathlib import Path

from detent.pipeline.result import Finding

_GO_STDERR_RE = re.compile(r"^(.+):(\d+):(\d+):\s+(.+)$")


def find_module_root(file_path: str) -> Path | None:
    """Walk up from file_path until go.mod found; return that dir or None."""
    current = Path(file_path).resolve().parent
    while True:
        if (current / "go.mod").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _pkg_path(file_path: str, module_root: Path) -> str:
    rel = Path(file_path).parent.resolve().relative_to(module_root)
    return "./" + str(rel) if str(rel) != "." else "."


def _not_found_finding(file_path: str, stage_name: str) -> Finding:
    return Finding(
        severity="warning",
        file=file_path,
        line=None,
        column=None,
        message="go not found — install from https://go.dev/dl",
        code="go/not-installed",
        stage=stage_name,
        fix_suggestion=None,
    )


def _no_mod_finding(file_path: str, stage_name: str) -> Finding:
    return Finding(
        severity="warning",
        file=file_path,
        line=None,
        column=None,
        message="no go.mod found — is this a Go module?",
        code="go/no-module",
        stage=stage_name,
        fix_suggestion=None,
    )


def _parse_go_stderr(stderr: bytes, file_path: str, stage_name: str, severity: str) -> list[Finding]:
    findings: list[Finding] = []
    for line in stderr.decode("utf-8", errors="replace").splitlines():
        m = _GO_STDERR_RE.match(line.strip())
        if m:
            findings.append(
                Finding(
                    severity=severity,  # type: ignore[arg-type]
                    file=file_path,
                    line=int(m.group(2)),
                    column=int(m.group(3)),
                    message=m.group(4),
                    code=None,
                    stage=stage_name,
                    fix_suggestion=None,
                )
            )
    return findings
