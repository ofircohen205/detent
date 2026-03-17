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

"""Go typecheck helper -- go build async runner."""

from __future__ import annotations

import asyncio
import contextlib
from pathlib import Path

import structlog

from detent.pipeline.result import Finding
from detent.stages.languages._go import (
    _no_mod_finding,
    _not_found_finding,
    _parse_go_stderr,
    _pkg_path,
    find_module_root,
)

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


async def run_build(file_path: str, content: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run go build on the package; compile errors -> error findings."""
    module_root = find_module_root(file_path)
    if module_root is None:
        return [_no_mod_finding(file_path, stage_name)]
    Path(file_path).write_text(content, encoding="utf-8")
    pkg = _pkg_path(file_path, module_root)
    logger.debug("[%s] go build %s (cwd=%s)", stage_name, pkg, module_root)
    try:
        proc = await asyncio.create_subprocess_exec(
            "go",
            "build",
            pkg,
            cwd=str(module_root),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return [_not_found_finding(file_path, stage_name)]
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.communicate()
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"go build timed out after {timeout}s",
                code="go/timeout",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]
    logger.debug("[%s] go build returncode=%s", stage_name, proc.returncode)
    if proc.returncode == 0:
        return []
    if proc.returncode is not None and proc.returncode >= 2:
        return [
            Finding(
                severity="warning",
                file=file_path,
                line=None,
                column=None,
                message=f"go build internal error: {stderr.decode('utf-8', errors='replace').strip()[:200]}",
                code="go/build-error",
                stage=stage_name,
                fix_suggestion=None,
            )
        ]
    return _parse_go_stderr(stderr, file_path, stage_name, "error")
