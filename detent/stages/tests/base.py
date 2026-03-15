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

"""TestsStage — dispatches to language-specific test runners."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from detent.config.languages import detect_language
from detent.pipeline.result import VerificationResult
from detent.stages.base import VerificationStage, _validate_file_path
from detent.stages.tests import _cargo_test as _rust
from detent.stages.tests import _go_test as _go
from detent.stages.tests import _jest, _pytest

if TYPE_CHECKING:
    from detent.schema import AgentAction

logger = logging.getLogger(__name__)


class TestsStage(VerificationStage):
    """Runs tests related to the modified file. Python->pytest, JS/TS->jest/vitest, Go->go test, Rust->cargo test."""

    name = "tests"

    def supports_language(self, lang: str) -> bool:
        return lang in {"python", "javascript", "typescript", "go", "rust"}

    async def _run(self, action: AgentAction) -> VerificationResult:
        """Find and run related tests by dispatching to the appropriate language helper."""
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

        lang = detect_language(file_path)
        timeout = self._config.timeout if self._config else 30

        if lang == "python":
            findings = await _pytest.run_pytest(file_path, self.name, timeout)
            tool = "pytest"
            if not findings:
                # No test files found or all passed — check if it was a skip
                duration_ms = (time.perf_counter() - start) * 1000
                return VerificationResult(
                    stage=self.name,
                    passed=True,
                    findings=[],
                    duration_ms=duration_ms,
                    metadata={"tool": tool, "language": lang},
                )
        elif lang in ("javascript", "typescript"):
            tool_override = self._config.tools[0] if self._config and self._config.tools else None
            findings = await _jest.run_jest(file_path, self.name, timeout, tool_override)
            tool = tool_override or "auto"
        elif lang == "go":
            findings = await _go.run_test(file_path, self.name, timeout)
            tool = "go test"
        elif lang == "rust":
            findings = await _rust.run_test(file_path, self.name, timeout)
            tool = "cargo test"
        else:
            findings = []
            tool = "none"

        duration_ms = (time.perf_counter() - start) * 1000
        return VerificationResult(
            stage=self.name,
            passed=len(findings) == 0,
            findings=findings,
            duration_ms=duration_ms,
            metadata={"tool": tool, "language": lang},
        )
