"""Result models for the verification pipeline.

Finding and VerificationResult are the outputs every VerificationStage produces.
They are pydantic models so they can be serialised to JSON for feedback synthesis.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """A single issue found by a verification stage."""

    severity: Literal["error", "warning", "info"]
    file: str
    line: int | None = None
    column: int | None = None
    message: str
    code: str | None = None
    stage: str
    fix_suggestion: str | None = None


class VerificationResult(BaseModel):
    """The result produced by a single VerificationStage.run() call."""

    stage: str
    passed: bool
    findings: list[Finding]
    duration_ms: float
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def errors(self) -> list[Finding]:
        """All findings with severity == 'error'."""
        return [f for f in self.findings if f.severity == "error"]

    @property
    def has_errors(self) -> bool:
        """True if any finding has severity == 'error'."""
        return any(f.severity == "error" for f in self.findings)
