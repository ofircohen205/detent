"""Unit tests for the FeedbackSynthesizer and StructuredFeedback."""

from detent.feedback.synthesizer import EnrichedFinding, StructuredFeedback


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
