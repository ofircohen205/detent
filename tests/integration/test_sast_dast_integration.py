"""Integration tests for SAST/DAST sub-stages (detect-secrets, pip-audit)."""

from __future__ import annotations

import shutil

import pytest

from detent.config import StageConfig
from detent.stages.security import SecurityStage
from tests.conftest import make_action


def _require_detect_secrets() -> None:
    if shutil.which("detect-secrets") is None:
        pytest.skip("detect-secrets not installed")


def _require_pip_audit() -> None:
    if shutil.which("pip-audit") is None:
        pytest.skip("pip-audit not installed")


def _secrets_only_stage() -> SecurityStage:
    return SecurityStage(
        StageConfig(
            name="security",
            enabled=True,
            timeout=30,
            options={
                "semgrep": {"enabled": False},
                "bandit": {"enabled": False},
                "secrets": {"enabled": True},
                "dep_scan": {"enabled": False},
            },
        )
    )


def _dep_scan_only_stage() -> SecurityStage:
    return SecurityStage(
        StageConfig(
            name="security",
            enabled=True,
            timeout=60,
            options={
                "semgrep": {"enabled": False},
                "bandit": {"enabled": False},
                "secrets": {"enabled": False},
                "dep_scan": {"enabled": True},
            },
        )
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_secret_scan_runs_and_reports_metadata(tmp_path) -> None:
    """detect-secrets scanner runs end-to-end and reports itself in metadata['tools']."""
    _require_detect_secrets()
    content = "def add(a: int, b: int) -> int:\n    return a + b\n"
    action = make_action(file_path=str(tmp_path / "utils.py"), content=content)

    result = await _secrets_only_stage().run(action)

    # The stage ran successfully — no error/warning findings from tool failure
    tool_error_findings = [f for f in result.findings if f.code in ("secrets/error", "secrets/not-installed")]
    assert tool_error_findings == [], f"detect-secrets tool error: {tool_error_findings}"
    assert "detect-secrets" in result.metadata["tools"]


@pytest.mark.asyncio
@pytest.mark.integration
async def test_secret_scan_clean_file_passes(tmp_path) -> None:
    """Clean Python file with no secrets produces no error findings."""
    _require_detect_secrets()
    content = "def add(a: int, b: int) -> int:\n    return a + b\n"
    action = make_action(file_path=str(tmp_path / "math_utils.py"), content=content)

    result = await _secrets_only_stage().run(action)

    assert not any(f.severity == "error" for f in result.findings)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dep_scan_clean_requirements_passes(tmp_path) -> None:
    """requirements.txt with no known-vulnerable packages passes dep scanning."""
    _require_pip_audit()
    content = "click>=8.1,<9\n"
    action = make_action(file_path=str(tmp_path / "requirements.txt"), content=content)

    result = await _dep_scan_only_stage().run(action)

    error_findings = [f for f in result.findings if f.severity == "error"]
    assert error_findings == [], f"Unexpected vulnerabilities found: {error_findings}"


@pytest.mark.asyncio
@pytest.mark.integration
async def test_dep_scan_skips_non_manifest(tmp_path) -> None:
    """Python source files do not trigger dep scanning."""
    _require_pip_audit()
    content = "import requests\nrequests.get('http://example.com')\n"
    action = make_action(file_path=str(tmp_path / "client.py"), content=content)

    result = await _dep_scan_only_stage().run(action)

    dep_findings = [f for f in result.findings if f.code and f.code.startswith("dep-scan/")]
    assert dep_findings == []


@pytest.mark.asyncio
@pytest.mark.integration
async def test_metadata_tools_listed_for_manifest(tmp_path) -> None:
    """metadata['tools'] contains both scanners when both are enabled."""
    _require_detect_secrets()
    _require_pip_audit()
    content = "click>=8.1,<9\n"
    action = make_action(file_path=str(tmp_path / "requirements.txt"), content=content)
    stage = SecurityStage(
        StageConfig(
            name="security",
            enabled=True,
            timeout=60,
            options={
                "semgrep": {"enabled": False},
                "bandit": {"enabled": False},
                "secrets": {"enabled": True},
                "dep_scan": {"enabled": True},
            },
        )
    )

    result = await stage.run(action)

    assert "detect-secrets" in result.metadata["tools"]
    assert "pip-audit" in result.metadata["tools"]
