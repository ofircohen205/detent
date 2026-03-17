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

"""Rust lint helper -- cargo clippy async runner."""

from __future__ import annotations

from pathlib import Path

import structlog

from detent.pipeline.result import Finding
from detent.stages.languages._rust import (
    _no_cargo_finding,
    _not_found_finding,
    _parse_cargo_json,
    _run_cargo,
    find_crate_root,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


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
