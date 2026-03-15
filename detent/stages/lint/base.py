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

"""LintStage — dispatches to language-specific lint helpers."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from detent.config.languages import detect_language
from detent.pipeline.result import VerificationResult
from detent.stages.base import VerificationStage, _validate_file_path
from detent.stages.lint import _eslint, _ruff

if TYPE_CHECKING:
    from detent.schema import AgentAction

logger = logging.getLogger(__name__)


class LintStage(VerificationStage):
    """Lints proposed file content. Python->ruff, JS/TS->eslint, Go->go vet, Rust->cargo clippy."""

    name = "lint"

    def supports_language(self, lang: str) -> bool:
        return lang in {"python", "javascript", "typescript", "go", "rust"}

    async def _run(self, action: AgentAction) -> VerificationResult:
        """Lint content by dispatching to the appropriate language helper."""
        start = time.perf_counter()
        file_path = action.file_path or ""
        content = action.content or ""
        if file_path:
            _validate_file_path(file_path)

        lang = detect_language(file_path)
        timeout = self._config.timeout if self._config else 30

        if lang == "python":
            findings = await _ruff.run_ruff(file_path, content, self.name, timeout)
            tool = "ruff"
        elif lang in ("javascript", "typescript"):
            findings = await _eslint.run_eslint(file_path, content, self.name, timeout)
            tool = "eslint"
        elif lang == "go":
            from detent.stages.lint import _go_vet as _go

            findings = await _go.run_vet(file_path, content, self.name, timeout)
            tool = "go vet"
        elif lang == "rust":
            from detent.stages.lint import _clippy as _rust

            findings = await _rust.run_clippy(file_path, content, self.name, timeout)
            tool = "cargo clippy"
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
