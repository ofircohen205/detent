"""Verification pipeline — orchestrates stage execution."""

from __future__ import annotations

import asyncio
import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from detent.config import DetentConfig, PipelineConfig
    from detent.schema import AgentAction
    from detent.stages.base import VerificationStage

from detent.pipeline.result import Finding, VerificationResult

logger = logging.getLogger(__name__)

_EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
}


def _detect_language(file_path: str) -> str:
    """Detect language from file extension. Returns 'unknown' for unrecognized types."""
    suffix = Path(file_path).suffix.lower()
    return _EXTENSION_TO_LANGUAGE.get(suffix, "unknown")


class VerificationPipeline:
    """Orchestrates verification stage execution against an AgentAction.

    Runs stages sequentially (default) or in parallel (config.parallel=True),
    aggregates findings into a single VerificationResult, and enforces
    fail-fast policy.
    """

    def __init__(
        self,
        stages: list[VerificationStage],
        config: PipelineConfig,
    ) -> None:
        self._stages = stages
        self._config = config

    @classmethod
    def from_config(cls, config: DetentConfig) -> VerificationPipeline:
        """Build a pipeline from DetentConfig using STAGE_REGISTRY.

        Unknown stage names are skipped with a warning. Disabled stages are
        excluded via config.get_enabled_stages().
        """
        from detent.stages import STAGE_REGISTRY

        stages: list[VerificationStage] = []
        for stage_cfg in config.get_enabled_stages():
            stage_cls = STAGE_REGISTRY.get(stage_cfg.name)
            if stage_cls is None:
                logger.warning("[pipeline] unknown stage '%s'; skipping", stage_cfg.name)
                continue
            stages.append(stage_cls())
        logger.info("[pipeline] built from config: %s", [s.name for s in stages])
        return cls(stages=stages, config=config.pipeline)

    async def run(self, action: AgentAction) -> VerificationResult:
        """Run all applicable stages and return an aggregate VerificationResult.

        Filters stages by language support, runs them per config, and aggregates
        all findings. Returns stage="pipeline" in the result.
        """
        start = time.perf_counter()
        lang = _detect_language(action.file_path or "")
        active = [s for s in self._stages if s.supports_language(lang)]

        logger.info(
            "[pipeline] running %d stage(s) for %s (%s)",
            len(active),
            action.file_path or "<unknown>",
            lang,
        )

        if not active:
            logger.info("[pipeline] no applicable stages; passing")
            return VerificationResult(
                stage="pipeline",
                passed=True,
                findings=[],
                duration_ms=(time.perf_counter() - start) * 1000,
            )

        if self._config.parallel:
            collected = await self._run_parallel(action, active)
        else:
            collected = await self._run_sequential(action, active)

        result = self._aggregate(collected, start)
        logger.info(
            "[pipeline] complete: passed=%s, %d finding(s) in %.1f ms",
            result.passed,
            len(result.findings),
            result.duration_ms,
        )
        return result

    async def _run_sequential(
        self,
        action: AgentAction,
        stages: list[VerificationStage],
    ) -> list[VerificationResult]:
        """Run stages sequentially, halting on error if fail_fast is enabled."""
        collected: list[VerificationResult] = []
        for stage in stages:
            result = await stage.run(action)
            collected.append(result)
            if self._config.fail_fast and result.has_errors:
                logger.info("[pipeline] fail-fast: halting after '%s'", stage.name)
                break
        return collected

    async def _run_parallel(
        self,
        action: AgentAction,
        stages: list[VerificationStage],
    ) -> list[VerificationResult]:
        """Run all stages concurrently, applying fail-fast to collected results."""
        # VerificationStage.run() catches all stage-level exceptions internally.
        # This guard exists as a belt-and-suspenders safety net in case a future
        # stage bypasses the base class. CancelledError is a BaseException and
        # will still propagate (intentional — parent cancellation should not be swallowed).
        try:
            results = await asyncio.gather(*[s.run(action) for s in stages])
        except Exception as exc:
            logger.error("[pipeline] gather failed: %s", exc, exc_info=True)
            return [
                VerificationResult(
                    stage="pipeline",
                    passed=False,
                    findings=[
                        Finding(
                            severity="error",
                            file=action.file_path or "<unknown>",
                            message=f"Pipeline gather failed: {exc}",
                            stage="pipeline",
                        )
                    ],
                    duration_ms=0.0,
                )
            ]
        collected = list(results)
        if self._config.fail_fast:
            truncated: list[VerificationResult] = []
            for r in collected:
                truncated.append(r)
                if r.has_errors:
                    # Include the first error result so callers know which stage failed.
                    break
            return truncated
        return collected

    def _aggregate(
        self,
        results: list[VerificationResult],
        start: float,
    ) -> VerificationResult:
        """Combine stage results into a single pipeline-level VerificationResult."""
        all_findings = [f for r in results for f in r.findings]
        passed = not any(r.has_errors for r in results)
        duration_ms = (time.perf_counter() - start) * 1000
        return VerificationResult(
            stage="pipeline",
            passed=passed,
            findings=all_findings,
            duration_ms=duration_ms,
            metadata={"stage_results": [r.model_dump() for r in results]},
        )
