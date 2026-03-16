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

"""Verification pipeline — orchestrates stage execution."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from detent.config import DetentConfig, PipelineConfig
    from detent.schema import AgentAction
    from detent.stages.base import VerificationStage

from detent.config.languages import detect_language
from detent.observability.metrics import record_pipeline_duration
from detent.observability.tracer import get_tracer
from detent.pipeline.result import Finding, VerificationResult

logger = logging.getLogger(__name__)


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
            stages.append(stage_cls(stage_cfg))
        logger.info("[pipeline] built from config: %s", [s.name for s in stages])
        return cls(stages=stages, config=config.pipeline)

    async def run(self, action: AgentAction) -> VerificationResult:
        """Run all applicable stages and return an aggregate VerificationResult.

        Filters stages by language support, runs them per config, and aggregates
        all findings. Returns stage="pipeline" in the result.
        """
        lang = detect_language(action.file_path or "")
        active = [s for s in self._stages if s.supports_language(lang)]

        tracer = get_tracer(__name__)
        with tracer.start_as_current_span(
            "detent.pipeline",
            attributes={
                "detent.file_path": action.file_path or "<unknown>",
                "detent.language": lang,
                "detent.stage_count": len(active),
                "detent.parallel": self._config.parallel,
            },
        ):
            start = time.perf_counter()

            logger.info(
                "[pipeline] running %d stage(s) for %s (%s)",
                len(active),
                action.file_path or "<unknown>",
                lang,
            )

            if not active:
                logger.info("[pipeline] no applicable stages; passing")
                result = VerificationResult(
                    stage="pipeline",
                    passed=True,
                    findings=[],
                    duration_ms=(time.perf_counter() - start) * 1000,
                )
            else:
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
        record_pipeline_duration(lang, result.passed, result.duration_ms)
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
