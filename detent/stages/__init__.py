"""Verification stages — composable checks for the pipeline."""

from detent.stages.base import VerificationStage
from detent.stages.lint import LintStage
from detent.stages.syntax import SyntaxStage
from detent.stages.tests import TestsStage
from detent.stages.typecheck import TypecheckStage

__all__ = [
    "LintStage",
    "SyntaxStage",
    "TestsStage",
    "TypecheckStage",
    "VerificationStage",
]
