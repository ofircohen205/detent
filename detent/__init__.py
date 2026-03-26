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

"""Detent — a verification runtime for AI coding agents.

Intercepts file writes, runs them through a configurable verification pipeline,
and rolls back atomically if the code fails.
"""

from __future__ import annotations

__version__ = "1.0.6"

from detent.adapters.base import AgentAdapter
from detent.adapters.hook.base import HookAdapter
from detent.adapters.hook.claude_code import ClaudeCodeHookAdapter
from detent.adapters.hook.codex import CodexHookAdapter
from detent.adapters.hook.gemini import GeminiAdapter
from detent.adapters.http.base import HTTPProxyAdapter
from detent.adapters.http.claude_code import ClaudeCodeAdapter
from detent.adapters.http.codex import CodexAdapter
from detent.adapters.langgraph import LangGraphAdapter
from detent.checkpoint.engine import CheckpointEngine
from detent.circuit_breaker import CircuitBreaker
from detent.config import DetentConfig, PipelineConfig, ProxyConfig, StageConfig, TelemetryConfig
from detent.feedback.schemas import EnrichedFinding, StructuredFeedback
from detent.feedback.synthesizer import FeedbackSynthesizer
from detent.ipc import IPCControlChannel
from detent.ipc.schemas import IPCMessageType
from detent.pipeline.pipeline import VerificationPipeline
from detent.pipeline.result import Finding, VerificationResult
from detent.proxy import DetentProxy, SessionManager
from detent.proxy.types import DetentSessionConflictError
from detent.schema import ActionType, AgentAction, RiskLevel
from detent.stages.base import VerificationStage
from detent.stages.lint import LintStage
from detent.stages.security import SecurityStage
from detent.stages.syntax import SyntaxStage
from detent.stages.tests import TestsStage
from detent.stages.typecheck import TypecheckStage

__all__ = [
    "__version__",
    # Config
    "DetentConfig",
    "ProxyConfig",
    "PipelineConfig",
    "StageConfig",
    "TelemetryConfig",
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
    "CircuitBreaker",
    "SyntaxStage",
    "LintStage",
    "SecurityStage",
    "TypecheckStage",
    "TestsStage",
    # Adapters
    "AgentAdapter",
    "ClaudeCodeAdapter",
    "ClaudeCodeHookAdapter",
    "CodexAdapter",
    "CodexHookAdapter",
    "LangGraphAdapter",
    "GeminiAdapter",
    "HTTPProxyAdapter",
    "HookAdapter",
    # Types
    "DetentSessionConflictError",
    "IPCMessageType",
]
