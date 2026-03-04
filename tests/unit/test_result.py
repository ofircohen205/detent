# tests/unit/test_result.py
"""Tests for Finding and VerificationResult models."""

from __future__ import annotations

from detent.pipeline.result import Finding, VerificationResult


def test_finding_defaults():
    f = Finding(severity="error", file="/src/main.py", message="bad code", stage="syntax")
    assert f.line is None
    assert f.column is None
    assert f.code is None
    assert f.fix_suggestion is None


def test_finding_full():
    f = Finding(
        severity="warning",
        file="/src/main.py",
        line=10,
        column=5,
        message="unused import",
        code="F401",
        stage="lint",
        fix_suggestion="Remove the import",
    )
    assert f.line == 10
    assert f.column == 5
    assert f.code == "F401"


def test_verification_result_passed():
    result = VerificationResult(stage="syntax", passed=True, findings=[], duration_ms=1.5)
    assert result.passed
    assert not result.has_errors
    assert result.errors == []


def test_verification_result_with_errors():
    error = Finding(severity="error", file="/src/main.py", message="syntax error", stage="syntax")
    result = VerificationResult(stage="syntax", passed=False, findings=[error], duration_ms=2.0)
    assert not result.passed
    assert result.has_errors
    assert len(result.errors) == 1


def test_verification_result_errors_filters_by_severity():
    findings = [
        Finding(severity="error", file="/src/main.py", message="bad", stage="lint"),
        Finding(severity="warning", file="/src/main.py", message="ok", stage="lint"),
        Finding(severity="info", file="/src/main.py", message="info", stage="lint"),
    ]
    result = VerificationResult(stage="lint", passed=False, findings=findings, duration_ms=5.0)
    assert len(result.errors) == 1
    assert result.errors[0].severity == "error"


def test_verification_result_metadata_defaults_empty():
    result = VerificationResult(stage="syntax", passed=True, findings=[], duration_ms=0.5)
    assert result.metadata == {}
