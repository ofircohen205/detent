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

"""TypecheckStage — dispatches to language-specific typecheck helpers."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from detent.config.languages import detect_language
from detent.pipeline.result import VerificationResult
from detent.stages.base import VerificationStage, _validate_file_path
from detent.stages.typecheck import _mypy, _tsc

if TYPE_CHECKING:
    from detent.schema import AgentAction

logger = logging.getLogger(__name__)


class TypecheckStage(VerificationStage):
    """Type-checks proposed file content. Python->mypy, JS/TS->tsc, Go->go build, Rust->cargo check."""

    name = "typecheck"

    def supports_language(self, lang: str) -> bool:
        return lang in {"python", "javascript", "typescript", "go", "rust"}

    async def _run(self, action: AgentAction) -> VerificationResult:
        """Type-check content by dispatching to the appropriate language helper."""
        start = time.perf_counter()
        file_path = action.file_path or ""
        content = action.content or ""
        if file_path:
            _validate_file_path(file_path)

        lang = detect_language(file_path)
        timeout = self._config.timeout if self._config else 30

        if lang == "python":
            findings = await _mypy.run_mypy(file_path, content, self.name, timeout)
            tool = "mypy"
        elif lang in ("javascript", "typescript"):
            findings = await _tsc.run_tsc(file_path, content, self.name, timeout)
            tool = "tsc"
        elif lang == "go":
            from detent.stages.typecheck import _go_build as _go

            findings = await _go.run_build(file_path, content, self.name, timeout)
            tool = "go build"
        elif lang == "rust":
            from detent.stages.typecheck import _cargo_check as _rust

            findings = await _rust.run_check(file_path, content, self.name, timeout)
            tool = "cargo check"
        else:
            findings = []
            tool = "none"

        duration_ms = (time.perf_counter() - start) * 1000
        return VerificationResult(
            stage=self.name,
            passed=not any(f.severity == "error" for f in findings),
            findings=findings,
            duration_ms=duration_ms,
            metadata={"tool": tool, "language": lang},
        )
