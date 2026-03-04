"""Verification stages — composable checks for the pipeline."""

from __future__ import annotations

from detent.stages.base import VerificationStage
from detent.stages.lint import LintStage
from detent.stages.syntax import SyntaxStage
from detent.stages.tests import TestsStage
from detent.stages.typecheck import TypecheckStage

STAGE_REGISTRY: dict[str, type[VerificationStage]] = {
    "syntax": SyntaxStage,
    "lint": LintStage,
    "typecheck": TypecheckStage,
    "tests": TestsStage,
}

__all__ = [
    "LintStage",
    "STAGE_REGISTRY",
    "SyntaxStage",
    "TestsStage",
    "TypecheckStage",
    "VerificationStage",
]
