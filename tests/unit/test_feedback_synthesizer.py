"""Unit tests for the FeedbackSynthesizer and StructuredFeedback."""

from detent.feedback.synthesizer import EnrichedFinding, FeedbackSynthesizer, StructuredFeedback
from detent.pipeline.result import Finding, VerificationResult
from detent.schema import ActionType, AgentAction, RiskLevel


def test_structured_feedback_model():
    feedback = StructuredFeedback(
        status="blocked",
        checkpoint="chk_001",
        summary="1 error found in syntax stage.",
        findings=[
            EnrichedFinding(
                severity="error",
                file="src/main.py",
                line=5,
                column=1,
                message="SyntaxError: invalid syntax",
                code=None,
                stage="syntax",
                fix_suggestion=None,
                context_lines=["line3", "line4", "BAD LINE", "line6", "line7"],
                context_start_line=3,
            )
        ],
        rollback_applied=False,
    )
    assert feedback.status == "blocked"
    assert len(feedback.findings) == 1
    assert feedback.findings[0].context_lines == ["line3", "line4", "BAD LINE", "line6", "line7"]


def _make_action(content: str = "x = 1\n") -> AgentAction:
    return AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="test-agent",
        tool_name="Write",
        tool_input={"file_path": "src/main.py", "content": content},
        tool_call_id="tc_001",
        session_id="sess_001",
        checkpoint_ref="chk_001",
        risk_level=RiskLevel.MEDIUM,
    )


def _make_result(findings: list[Finding], passed: bool = True) -> VerificationResult:
    return VerificationResult(
        stage="pipeline",
        passed=passed,
        findings=findings,
        duration_ms=42.0,
    )


def test_findings_sorted_by_severity():
    result = _make_result(
        findings=[
            Finding(severity="info", file="f.py", message="info msg", stage="lint"),
            Finding(severity="error", file="f.py", message="err msg", stage="syntax"),
            Finding(severity="warning", file="f.py", message="warn msg", stage="lint"),
        ]
    )
    feedback = FeedbackSynthesizer().synthesize(result, _make_action())
    severities = [f.severity for f in feedback.findings]
    assert severities == ["error", "warning", "info"]


def test_error_finding_gets_context_lines():
    content = "\n".join(f"line{i}" for i in range(1, 12))  # line1..line11
    result = _make_result(
        findings=[
            Finding(severity="error", file="f.py", line=6, message="err", stage="syntax")
        ]
    )
    feedback = FeedbackSynthesizer().synthesize(result, _make_action(content))
    ef = feedback.findings[0]
    # ±3 around line 6 → lines 3..9
    assert ef.context_start_line == 3
    assert ef.context_lines == ["line3", "line4", "line5", "line6", "line7", "line8", "line9"]


def test_warning_finding_gets_no_context():
    result = _make_result(
        findings=[
            Finding(severity="warning", file="f.py", line=5, message="w", stage="lint")
        ],
        passed=True,
    )
    feedback = FeedbackSynthesizer().synthesize(result, _make_action())
    assert feedback.findings[0].context_lines == []
    assert feedback.findings[0].context_start_line is None


def test_error_finding_without_line_gets_no_context():
    result = _make_result(
        findings=[Finding(severity="error", file="f.py", message="err", stage="syntax")]
    )
    feedback = FeedbackSynthesizer().synthesize(result, _make_action())
    assert feedback.findings[0].context_lines == []


def test_context_clamps_at_file_boundaries():
    content = "line1\nline2\nline3"
    result = _make_result(
        findings=[
            Finding(severity="error", file="f.py", line=1, message="err", stage="syntax")
        ]
    )
    feedback = FeedbackSynthesizer().synthesize(result, _make_action(content))
    ef = feedback.findings[0]
    assert ef.context_start_line == 1
    assert ef.context_lines == ["line1", "line2", "line3"]  # clamped, only 3 lines exist


def test_summary_all_passed():
    result = _make_result(findings=[], passed=True)
    feedback = FeedbackSynthesizer().synthesize(result, _make_action())
    assert "passed" in feedback.summary.lower()
    assert "src/main.py" in feedback.summary


def test_summary_blocked_with_errors():
    result = _make_result(
        findings=[
            Finding(severity="error", file="f.py", message="err", stage="syntax"),
            Finding(severity="error", file="f.py", message="err2", stage="syntax"),
        ]
    )
    feedback = FeedbackSynthesizer().synthesize(result, _make_action())
    assert feedback.status == "blocked"
    assert "2 error" in feedback.summary
    assert "blocked" in feedback.summary.lower()


def test_summary_warning_only():
    result = _make_result(
        findings=[
            Finding(severity="warning", file="f.py", message="w", stage="lint")
        ],
        passed=True,
    )
    feedback = FeedbackSynthesizer().synthesize(result, _make_action())
    assert feedback.status == "warning"
    assert "1 warning" in feedback.summary


def test_summary_mixed_errors_and_warnings():
    result = _make_result(
        findings=[
            Finding(severity="error", file="f.py", message="e", stage="syntax"),
            Finding(severity="warning", file="f.py", message="w", stage="lint"),
        ]
    )
    feedback = FeedbackSynthesizer().synthesize(result, _make_action())
    assert "1 error" in feedback.summary
    assert "1 warning" in feedback.summary


def test_status_blocked_when_errors():
    result = _make_result(
        findings=[Finding(severity="error", file="f.py", message="e", stage="syntax")]
    )
    feedback = FeedbackSynthesizer().synthesize(result, _make_action())
    assert feedback.status == "blocked"


def test_status_warning_when_only_warnings():
    result = _make_result(
        findings=[Finding(severity="warning", file="f.py", message="w", stage="lint")],
        passed=True,
    )
    feedback = FeedbackSynthesizer().synthesize(result, _make_action())
    assert feedback.status == "warning"


def test_status_passed_when_no_findings():
    result = _make_result(findings=[], passed=True)
    feedback = FeedbackSynthesizer().synthesize(result, _make_action())
    assert feedback.status == "passed"


def test_rollback_applied_default_false():
    result = _make_result(findings=[], passed=True)
    feedback = FeedbackSynthesizer().synthesize(result, _make_action())
    assert feedback.rollback_applied is False


def test_checkpoint_ref_propagated():
    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="test",
        tool_name="Write",
        tool_input={"file_path": "f.py", "content": "x=1"},
        tool_call_id="tc_002",
        session_id="sess_002",
        checkpoint_ref="chk_my_ref",
        risk_level=RiskLevel.LOW,
    )
    result = _make_result(findings=[], passed=True)
    feedback = FeedbackSynthesizer().synthesize(result, action)
    assert feedback.checkpoint == "chk_my_ref"


def test_importable_from_detent_feedback():
    from detent.feedback import FeedbackSynthesizer, StructuredFeedback  # noqa: F401

    assert FeedbackSynthesizer is not None
    assert StructuredFeedback is not None
