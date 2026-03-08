"""Detent — a verification runtime for AI coding agents.

Intercepts file writes, runs them through a configurable verification pipeline,
and rolls back atomically if the code fails.
"""

from __future__ import annotations

__version__ = "0.1.0"

# Configuration
from detent.checkpoint.engine import CheckpointEngine
from detent.config import DetentConfig, PipelineConfig, ProxyConfig, StageConfig
from detent.feedback.synthesizer import (
    EnrichedFinding,
    FeedbackSynthesizer,
    StructuredFeedback,
)
from detent.ipc import IPCControlChannel
from detent.pipeline.pipeline import VerificationPipeline
from detent.pipeline.result import Finding, VerificationResult
from detent.proxy import DetentProxy, SessionManager
from detent.proxy.types import DetentSessionConflictError, IPCMessageType
from detent.schema import ActionType, AgentAction, RiskLevel
from detent.stages.lint import LintStage
from detent.stages.syntax import SyntaxStage
from detent.stages.tests import TestsStage
from detent.stages.typecheck import TypecheckStage

# Stages base class
from detent.stages.base import VerificationStage

# Adapters
from detent.adapters.base import AgentAdapter
from detent.adapters.claude_code import ClaudeCodeAdapter
from detent.adapters.langgraph import LangGraphAdapter

__all__ = [
    "__version__",
    # Config
    "DetentConfig",
    "ProxyConfig",
    "PipelineConfig",
    "StageConfig",
    # Schema
    "AgentAction",
    "ActionType",
    "RiskLevel",
    # Runtime
    "DetentProxy",
    "SessionManager",
    "IPCControlChannel",
    # Checkpoint
    "CheckpointEngine",
    # Pipeline
    "VerificationPipeline",
    "VerificationResult",
    "Finding",
    # Feedback
    "FeedbackSynthesizer",
    "StructuredFeedback",
    "EnrichedFinding",
    # Stages
    "VerificationStage",
    "SyntaxStage",
    "LintStage",
    "TypecheckStage",
    "TestsStage",
    # Adapters
    "AgentAdapter",
    "ClaudeCodeAdapter",
    "LangGraphAdapter",
    # Types
    "DetentSessionConflictError",
    "IPCMessageType",
]
