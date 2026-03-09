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

"""TestsStage — runs pytest on test files related to the modified source file.

Discovery: given action.file_path, walk up at most 5 levels looking for a
tests/ directory, then search for test_{stem}.py files inside it.
If none found, skip gracefully (return passed with skipped metadata).
"""

from __future__ import annotations

import asyncio
import glob as _glob
import logging
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from detent.schema import AgentAction

from detent.pipeline.result import Finding, VerificationResult
from detent.stages.base import VerificationStage, _validate_file_path

logger = logging.getLogger(__name__)

_MAX_WALK_DEPTH = 5
_PASSING_EXIT_CODES = frozenset({0, 5})  # 0=all passed, 5=no tests collected


class TestsStage(VerificationStage):
    """Runs pytest on test files related to the modified source file.

    If no related test file is found, returns passed=True with skipped metadata.
    pytest exit code 5 (no tests collected) is also treated as passed.
    """

    name = "tests"

    async def _run(self, action: AgentAction) -> VerificationResult:
        """Find related test files and run pytest on them."""
        start = time.perf_counter()

        file_path = action.file_path or ""
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

        test_files = self._find_test_files(file_path)
        if not test_files:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.debug("[tests] no test files found for %s", file_path)
            return VerificationResult(
                stage=self.name,
                passed=True,
                findings=[],
                duration_ms=duration_ms,
                metadata={"skipped": True, "reason": f"No test files found for {Path(file_path).name}"},
            )

        logger.debug("[tests] running pytest on %s", [str(f) for f in test_files])

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "pytest",
            *[str(f) for f in test_files],
            "--tb=short",
            "-q",
            "--no-header",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()

        duration_ms = (time.perf_counter() - start) * 1000
        output = stdout.decode("utf-8", errors="replace")

        passed = proc.returncode in _PASSING_EXIT_CODES
        if not passed and stderr:
            logger.debug("[tests] pytest stderr: %s", stderr.decode("utf-8", errors="replace").strip())
        findings = [] if passed else self._parse_failures(output, file_path)

        return VerificationResult(
            stage=self.name,
            passed=passed,
            findings=findings,
            duration_ms=duration_ms,
            metadata={
                "returncode": proc.returncode,
                "test_files": [str(f) for f in test_files],
            },
        )

    def _find_test_files(self, file_path: str) -> list[Path]:
        """Find test files related to the given source file.

        Walks up from source file's directory, looking for a tests/ dir,
        then searches for files named test_{stem}.py inside it.
        """
        path = Path(file_path)
        if path.suffix != ".py":
            return []

        stem = path.stem
        candidate = path.parent

        for _ in range(_MAX_WALK_DEPTH):
            tests_dir = candidate / "tests"
            if tests_dir.is_dir():
                matches = list(tests_dir.rglob(f"test_{_glob.escape(stem)}.py"))
                if matches:
                    return matches
            parent = candidate.parent
            if parent == candidate:
                break
            candidate = parent

        return []

    def _parse_failures(self, output: str, file_path: str) -> list[Finding]:
        """Extract failed test names from pytest --tb=short -q output.

        Lines starting with 'FAILED ' contain the test node ID followed by
        ' - ' and the error message.
        """
        findings = []
        for line in output.splitlines():
            if line.startswith("FAILED "):
                parts = line[7:].split(" - ", 1)
                test_name = parts[0].strip()
                error_detail = parts[1].strip() if len(parts) > 1 else ""
                message = f"Test failed: {test_name}"
                if error_detail:
                    message += f" \u2014 {error_detail}"
                findings.append(
                    Finding(
                        severity="error",
                        file=file_path,
                        line=None,
                        column=None,
                        message=message,
                        code=None,
                        stage=self.name,
                        fix_suggestion=None,
                    )
                )
        return findings
