"""Integration tests for SecurityStage with real tools."""

from __future__ import annotations

import shutil

import pytest

from detent.config import StageConfig
from detent.stages.security import SecurityStage
from tests.conftest import make_action


def _require_tools() -> None:
    if shutil.which("semgrep") is None or shutil.which("bandit") is None:
        pytest.skip("semgrep/bandit not installed")


def _security_stage(rule_path: str) -> SecurityStage:
    return SecurityStage(
        StageConfig(
            name="security",
            enabled=True,
            timeout=30,
            options={
                "semgrep": {"enabled": True, "rulesets": [rule_path]},
                "bandit": {"enabled": True, "confidence": "low"},
            },
        )
    )


@pytest.mark.asyncio
@pytest.mark.integration
async def test_security_stage_flags_vulnerable_code(tmp_path) -> None:
    _require_tools()
    rule_path = tmp_path / "rules.yml"
    rule_path.write_text(
        "\n".join(
            [
                "rules:",
                "  - id: subprocess-shell-true",
                "    pattern: subprocess.Popen(..., shell=True)",
                "    message: subprocess with shell=True",
                "    languages: [python]",
                "    severity: ERROR",
            ]
        )
        + "\n"
    )

    content = "import subprocess\nsubprocess.Popen('ls', shell=True)\n"
    action = make_action(file_path=str(tmp_path / "vuln.py"), content=content)
    stage = _security_stage(str(rule_path))

    result = await stage.run(action)
    assert any(f.code and f.code.startswith("semgrep/") for f in result.findings)
    assert any(f.code and f.code.startswith("bandit/") for f in result.findings)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_security_stage_clean_code_passes(tmp_path) -> None:
    _require_tools()
    rule_path = tmp_path / "rules.yml"
    rule_path.write_text(
        "\n".join(
            [
                "rules:",
                "  - id: subprocess-shell-true",
                "    pattern: subprocess.Popen(..., shell=True)",
                "    message: subprocess with shell=True",
                "    languages: [python]",
                "    severity: ERROR",
            ]
        )
        + "\n"
    )

    content = "def add(a, b):\n    return a + b\n"
    action = make_action(file_path=str(tmp_path / "clean.py"), content=content)
    stage = _security_stage(str(rule_path))

    result = await stage.run(action)
    assert result.passed
    assert result.findings == []
