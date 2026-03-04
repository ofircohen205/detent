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

    name: str

    async def run(self, action: AgentAction) -> VerificationResult:
        """Execute the stage, catching all exceptions."""
        start = time.perf_counter()
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
        return result

    @abstractmethod
    async def _run(self, action: AgentAction) -> VerificationResult:
        """Subclass-specific verification logic. May raise freely."""
        ...

    def supports_language(self, lang: str) -> bool:
        """Return True if this stage supports the given language. Default: all."""
        return True
