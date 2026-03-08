"""Test that all SDK exports are available."""

import pytest


def test_all_exports_importable():
    """Verify all public SDK exports can be imported."""
    from detent import (
        # Config
        DetentConfig,
        ProxyConfig,
        PipelineConfig,
        StageConfig,
        # Schema
        AgentAction,
        ActionType,
        RiskLevel,
        # Runtime
        DetentProxy,
        SessionManager,
        IPCControlChannel,
        # Checkpoint
        CheckpointEngine,
        # Pipeline
        VerificationPipeline,
        VerificationResult,
        Finding,
        # Feedback
        FeedbackSynthesizer,
        StructuredFeedback,
        EnrichedFinding,
        # Stages
        VerificationStage,
        SyntaxStage,
        LintStage,
        TypecheckStage,
        TestsStage,
        # Adapters
        AgentAdapter,
        ClaudeCodeAdapter,
        LangGraphAdapter,
        # Types
        DetentSessionConflictError,
        IPCMessageType,
    )

    # Smoke test: verify they're not None
    assert DetentConfig is not None
    assert ActionType is not None
    assert VerificationPipeline is not None


def test_all_in_all():
    """Verify __all__ contains all exports."""
    import detent

    expected = {
        "__version__",
        "DetentConfig",
        "ProxyConfig",
        "PipelineConfig",
        "StageConfig",
        "AgentAction",
        "ActionType",
        "RiskLevel",
        "DetentProxy",
        "SessionManager",
        "IPCControlChannel",
        "CheckpointEngine",
        "VerificationPipeline",
        "VerificationResult",
        "Finding",
        "FeedbackSynthesizer",
        "StructuredFeedback",
        "EnrichedFinding",
        "VerificationStage",
        "SyntaxStage",
        "LintStage",
        "TypecheckStage",
        "TestsStage",
        "AgentAdapter",
        "ClaudeCodeAdapter",
        "LangGraphAdapter",
        "DetentSessionConflictError",
        "IPCMessageType",
    }

    assert set(detent.__all__) == expected
