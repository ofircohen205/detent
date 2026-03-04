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


def _make_result(findings: list[Finding], passed: bool = False) -> VerificationResult:
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
