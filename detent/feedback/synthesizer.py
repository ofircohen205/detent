"""Feedback synthesis engine.

Converts raw VerificationResult findings into structured, LLM-optimized
feedback for agent self-repair. All synthesis is deterministic (no LLM calls)
in v0.1.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult
    from detent.schema import AgentAction

logger = logging.getLogger(__name__)


class EnrichedFinding(BaseModel):
    """A Finding enriched with source context lines for agent feedback."""

    severity: Literal["error", "warning", "info"]
    file: str
    line: int | None = None
    column: int | None = None
    message: str
    code: str | None = None
    stage: str
    fix_suggestion: str | None = None
    context_lines: list[str] = []
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
