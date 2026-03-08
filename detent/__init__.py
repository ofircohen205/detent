"""Detent — a verification runtime for AI coding agents.

Intercepts file writes, runs them through a configurable verification pipeline,
and rolls back atomically if the code fails.
"""

from __future__ import annotations

__version__ = "0.1.0"

# Pipeline result models
from detent.pipeline.result import Finding, VerificationResult

# Verification stages
from detent.stages.base import VerificationStage
from detent.stages.lint import LintStage
from detent.stages.syntax import SyntaxStage
from detent.stages.tests import TestsStage
from detent.stages.typecheck import TypecheckStage

# Proxy and IPC
from detent.ipc import IPCControlChannel
from detent.proxy import DetentProxy, SessionManager
from detent.proxy.types import DetentSessionConflictError, IPCMessageType

__all__ = [
    "__version__",
    "DetentProxy",
    "DetentSessionConflictError",
    "Finding",
    "IPCControlChannel",
    "IPCMessageType",
    "LintStage",
    "SessionManager",
    "SyntaxStage",
    "TestsStage",
    "TypecheckStage",
    "VerificationResult",
    "VerificationStage",
]
