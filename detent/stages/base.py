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
from typing import TYPE_CHECKING, Literal

from detent.circuit_breaker import CircuitBreaker, CircuitOpenError
from detent.config.languages import detect_language
from detent.observability.metrics import record_stage_duration, record_stage_findings
from detent.observability.tracer import get_tracer
from detent.pipeline.result import Finding, VerificationResult

if TYPE_CHECKING:
    from detent.config import StageConfig
    from detent.schema import AgentAction

logger = logging.getLogger(__name__)


def _validate_file_path(path: str) -> None:
    """Reject file_path values that could cause traversal or injection.

    Raises:
        ValueError: If the path contains null bytes, path traversal segments,
            or glob metacharacters.
    """
    if "\x00" in path:
        raise ValueError(f"file_path contains null byte: {path!r}")
    parts = path.replace("\\", "/").split("/")
    if ".." in parts:
        raise ValueError(f"file_path contains path traversal: {path!r}")
    for char in ("*", "?", "[", "]"):
        if char in path:
            raise ValueError(f"file_path contains glob metacharacter {char!r}: {path!r}")


class VerificationStage(ABC):
    """Base class for a single verification stage.

    Subclasses implement _run(). The public run() wraps _run() with
    exception handling so a stage crash never propagates to the pipeline.
    """

    def __init__(self, config: StageConfig | None = None) -> None:
        self._config = config
        self._circuit_breaker: CircuitBreaker | None = None
        self._circuit_behavior: Literal["skip", "warn"] = "warn"
        if config and config.circuit_breaker.enabled:
            cb_cfg = config.circuit_breaker
            self._circuit_behavior = cb_cfg.behavior
            self._circuit_breaker = CircuitBreaker(
                name=f"stage:{self.name}",
                failure_threshold=cb_cfg.failure_threshold,
                recovery_window_s=cb_cfg.recovery_window_s,
            )

    @property
    @abstractmethod
    def name(self) -> str:
        """The stage name, e.g. 'syntax', 'lint', 'typecheck', 'tests'."""
        ...

    async def run(self, action: AgentAction) -> VerificationResult:
        """Execute the stage, catching exceptions and logging circuit state."""
        start = time.perf_counter()
        logger.debug("[%s] starting on %s", self.name, action.file_path)
        tracer = get_tracer(__name__)
        language = detect_language(action.file_path)
        circuit_state = self._circuit_breaker.state if self._circuit_breaker else "disabled"
        with tracer.start_as_current_span(
            f"detent.stage.{self.name}",
            attributes={
                "detent.stage.name": self.name,
                "detent.stage.language": language,
                "detent.stage.circuit_breaker": "enabled" if self._circuit_breaker else "disabled",
                "detent.circuit_breaker.state": circuit_state,
            },
        ) as span:
            try:
                if self._circuit_breaker:
                    result = await self._circuit_breaker.call(self._run(action))
                else:
                    result = await self._run(action)
            except CircuitOpenError:
                result = self._handle_open_circuit(action)
            except Exception as exc:
                logger.error("[%s] unexpected error: %s", self.name, exc, exc_info=True)
                duration_ms = (time.perf_counter() - start) * 1000
                result = VerificationResult(
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
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                record_stage_duration(self.name, language, result.passed, duration_ms)
                for finding in result.findings:
                    record_stage_findings(self.name, finding.severity)
                span.set_attribute("detent.stage.passed", result.passed)
                span.set_attribute("detent.stage.findings", len(result.findings))
                span.set_attribute(
                    "detent.circuit_breaker.state",
                    self._circuit_breaker.state if self._circuit_breaker else "disabled",
                )
            logger.info(
                "[%s] %s — %d finding(s) in %.1f ms",
                self.name,
                action.file_path,
                len(result.findings),
                duration_ms,
            )
            return result

    def _handle_open_circuit(self, action: AgentAction) -> VerificationResult:
        message = f"{self.name} circuit breaker open — stage skipped"
        if self._circuit_behavior == "skip":
            return VerificationResult(
                stage=self.name,
                passed=True,
                findings=[],
                duration_ms=0.0,
            )
        finding = Finding(
            severity="warning",
            file=action.file_path or "<unknown>",
            line=None,
            column=None,
            message=message,
            code="circuit-breaker-open",
            stage=self.name,
            fix_suggestion=None,
        )
        return VerificationResult(
            stage=self.name,
            passed=True,
            findings=[finding],
            duration_ms=0.0,
        )

    @abstractmethod
    async def _run(self, action: AgentAction) -> VerificationResult:
        """Subclass-specific verification logic. May raise freely."""
        ...

    def supports_language(self, lang: str) -> bool:
        """Return True if this stage supports the given language. Default: all."""
        return True
