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

"""Abstract base class for all verification stages."""

from __future__ import annotations

import logging
import time
from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from detent.pipeline.result import Finding, VerificationResult

if TYPE_CHECKING:
    from detent.schema import AgentAction

logger = logging.getLogger(__name__)


class VerificationStage(ABC):
    """Base class for a single verification stage.

    Subclasses implement _run(). The public run() wraps _run() with
    exception handling so a stage crash never propagates to the pipeline.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The stage name, e.g. 'syntax', 'lint', 'typecheck', 'tests'."""
        ...

    async def run(self, action: AgentAction) -> VerificationResult:
        """Execute the stage, catching all exceptions."""
        start = time.perf_counter()
        logger.debug("[%s] starting on %s", self.name, action.file_path)
        try:
            result = await self._run(action)
        except Exception as exc:
            logger.error("[%s] unexpected error: %s", self.name, exc, exc_info=True)
            duration_ms = (time.perf_counter() - start) * 1000
            return VerificationResult(
                stage=self.name,
                passed=False,
                findings=[
                    Finding(
                        severity="error",
                        file=action.file_path or "<unknown>",
                        line=None,
                        column=None,
                        message=f"Stage '{self.name}' failed unexpectedly: {exc}",
                        code=None,
                        stage=self.name,
                        fix_suggestion=None,
                    )
                ],
                duration_ms=duration_ms,
                metadata={"error": str(exc)},
            )
        logger.info(
            "[%s] %s — %d finding(s) in %.1f ms",
            self.name,
            action.file_path,
            len(result.findings),
            result.duration_ms,
        )
        return result

    @abstractmethod
    async def _run(self, action: AgentAction) -> VerificationResult:
        """Subclass-specific verification logic. May raise freely."""
        ...

    def supports_language(self, lang: str) -> bool:
        """Return True if this stage supports the given language. Default: all."""
        return True
