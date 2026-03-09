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

"""Feedback synthesis engine.

Converts raw VerificationResult findings into structured, LLM-optimized
feedback for agent self-repair. All synthesis is deterministic (no LLM calls)
in v0.1.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from detent.pipeline.result import Finding, VerificationResult
    from detent.schema import AgentAction

logger = logging.getLogger(__name__)

_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


class EnrichedFinding(BaseModel):
    """A Finding enriched with surrounding source lines for agent self-repair.

    context_lines holds the source lines surrounding the finding (±3 lines).
    context_start_line is the 1-based line number of context_lines[0].
    Only error-severity findings with a known line number are enriched.
    """

    severity: Literal["error", "warning", "info"]
    file: str
    line: int | None = None
    column: int | None = None
    message: str
    code: str | None = None
    stage: str
    fix_suggestion: str | None = None
    context_lines: list[str] = Field(default_factory=list)
    context_start_line: int | None = None


class StructuredFeedback(BaseModel):
    """LLM-optimized structured feedback produced by FeedbackSynthesizer.

    Serializable to JSON — compatible with Claude Code additionalContext.
    """

    status: Literal["blocked", "passed", "warning"]
    checkpoint: str
    summary: str
    findings: list[EnrichedFinding]
    rollback_applied: bool


class FeedbackSynthesizer:
    """Converts VerificationResult + AgentAction into StructuredFeedback."""

    def synthesize(
        self,
        result: VerificationResult,
        action: AgentAction,
    ) -> StructuredFeedback:
        """Produce structured, LLM-optimized feedback from a pipeline result."""
        logger.debug(
            "[feedback] synthesizing for %s: passed=%s, %d finding(s)",
            action.file_path,
            result.passed,
            len(result.findings),
        )

        sorted_findings = sorted(
            result.findings,
            key=lambda f: _SEVERITY_ORDER.get(f.severity, 99),
        )

        enriched = [self._enrich(f, action) for f in sorted_findings]
        status = self._determine_status(result)
        summary = self._generate_summary(result, action)

        feedback = StructuredFeedback(
            status=status,
            checkpoint=action.checkpoint_ref,
            summary=summary,
            findings=enriched,
            rollback_applied=False,
        )
        logger.info("[feedback] status=%s, %d enriched finding(s)", status, len(enriched))
        return feedback

    def _determine_status(self, result: VerificationResult) -> Literal["blocked", "passed", "warning"]:
        if result.has_errors:
            return "blocked"
        if any(f.severity == "warning" for f in result.findings):
            return "warning"
        return "passed"

    def _enrich(self, finding: Finding, action: AgentAction) -> EnrichedFinding:
        context_lines: list[str] = []
        context_start_line: int | None = None
        if finding.severity == "error" and finding.line is not None and action.content:
            context_lines, context_start_line = _extract_context(action.content, finding.line)
        return EnrichedFinding(
            severity=finding.severity,
            file=finding.file,
            line=finding.line,
            column=finding.column,
            message=finding.message,
            code=finding.code,
            stage=finding.stage,
            fix_suggestion=finding.fix_suggestion,
            context_lines=context_lines,
            context_start_line=context_start_line,
        )

    def _generate_summary(self, result: VerificationResult, action: AgentAction) -> str:
        file_path = action.file_path or "<unknown>"
        errors = [f for f in result.findings if f.severity == "error"]
        warnings = [f for f in result.findings if f.severity == "warning"]

        if not result.findings:
            return f"All verification checks passed for `{file_path}`."

        parts: list[str] = []
        if errors:
            stages = sorted({f.stage for f in errors})
            parts.append(f"{len(errors)} error(s) found in {_join_stages(stages)} stage(s)")
        if warnings:
            stages = sorted({f.stage for f in warnings})
            parts.append(f"{len(warnings)} warning(s) from {_join_stages(stages)} stage(s)")

        verdict = "File write blocked." if result.has_errors else "File write allowed with warnings."
        return f"`{file_path}`: {'; '.join(parts)}. {verdict}"


def _extract_context(content: str, line: int, radius: int = 3) -> tuple[list[str], int]:
    """Return ±radius lines around the given 1-based line number.

    Returns (lines, start_line) where start_line is 1-based.
    """
    lines = content.splitlines()
    zero = line - 1  # convert to 0-based
    start = max(0, zero - radius)
    end = min(len(lines), zero + radius + 1)
    return lines[start:end], start + 1  # return 1-based start


def _join_stages(stages: list[str]) -> str:
    """Format a list of stage names for human-readable output."""
    if len(stages) == 1:
        return f"`{stages[0]}`"
    return ", ".join(f"`{s}`" for s in stages[:-1]) + f" and `{stages[-1]}`"
