"""Test that all SDK exports are available."""


def test_all_exports_importable():
    """Verify all public SDK exports can be imported."""
    from detent import (
        ActionType,
        AgentAction,
        AgentAdapter,
        CheckpointEngine,
        ClaudeCodeAdapter,
        DetentConfig,
        DetentProxy,
        DetentSessionConflictError,
        EnrichedFinding,
        FeedbackSynthesizer,
        Finding,
        IPCControlChannel,
        IPCMessageType,
        LangGraphAdapter,
        LintStage,
        PipelineConfig,
        ProxyConfig,
        RiskLevel,
        SessionManager,
        StageConfig,
        StructuredFeedback,
        SyntaxStage,
        TestsStage,
        TypecheckStage,
        VerificationPipeline,
        VerificationResult,
        VerificationStage,
    )

    # Verify all 26 imports are not None
    assert all(
        x is not None
        for x in [
            DetentConfig,
            ProxyConfig,
            PipelineConfig,
            StageConfig,
            AgentAction,
            ActionType,
            RiskLevel,
            DetentProxy,
            SessionManager,
            IPCControlChannel,
            CheckpointEngine,
            VerificationPipeline,
            VerificationResult,
            Finding,
            FeedbackSynthesizer,
            StructuredFeedback,
            EnrichedFinding,
            VerificationStage,
            SyntaxStage,
            LintStage,
            TypecheckStage,
            TestsStage,
            AgentAdapter,
            ClaudeCodeAdapter,
            LangGraphAdapter,
            DetentSessionConflictError,
            IPCMessageType,
        ]
    )


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
        "CircuitBreaker",
        "LangGraphAdapter",
        "TelemetryConfig",
        "DetentSessionConflictError",
        "IPCMessageType",
    }

    assert set(detent.__all__) == expected
