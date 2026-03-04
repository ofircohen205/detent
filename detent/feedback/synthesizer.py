"""Feedback synthesis engine.

Converts raw VerificationResult findings into structured, LLM-optimized
feedback for agent self-repair. All synthesis is deterministic (no LLM calls)
in v0.1.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult
    from detent.schema import AgentAction


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
