"""Tests for SecurityStage — Semgrep + Bandit parsing and behavior."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from detent.config import StageConfig
from detent.stages.security import SecurityStage
from tests.conftest import make_action


class FakeProc:
    def __init__(
        self,
        *,
        returncode: int | None = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
    ) -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr
        self.killed = False

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.killed = True


def _stage_with_options(options: dict[str, object]) -> SecurityStage:
    return SecurityStage(StageConfig(name="security", enabled=True, timeout=1, options=options))


@pytest.mark.asyncio
async def test_both_tools_disabled_skips() -> None:
    stage = _stage_with_options(
        {
            "semgrep": {"enabled": False},
            "bandit": {"enabled": False},
            "secrets": {"enabled": False},
            "dep_scan": {"enabled": False},
        }
    )
    action = make_action(file_path="/src/main.py", content="print('hi')\n")
    result = await stage.run(action)
    assert result.passed
    assert result.findings == []
    assert result.metadata.get("skipped") is True


@pytest.mark.asyncio
async def test_semgrep_disabled_runs_only_bandit() -> None:
    stage = _stage_with_options({"semgrep": {"enabled": False}, "bandit": {"enabled": True}})
    stage._run_semgrep = AsyncMock(return_value=[])
    stage._run_bandit = AsyncMock(return_value=[])
    action = make_action(file_path="/src/main.py", content="print('hi')\n")
    await stage.run(action)
    stage._run_semgrep.assert_not_called()
    stage._run_bandit.assert_called_once()


@pytest.mark.asyncio
async def test_bandit_disabled_runs_only_semgrep() -> None:
    stage = _stage_with_options({"semgrep": {"enabled": True}, "bandit": {"enabled": False}})
    stage._run_semgrep = AsyncMock(return_value=[])
    stage._run_bandit = AsyncMock(return_value=[])
    action = make_action(file_path="/src/main.py", content="print('hi')\n")
    await stage.run(action)
    stage._run_semgrep.assert_called_once()
    stage._run_bandit.assert_not_called()


@pytest.mark.asyncio
async def test_non_python_skips_bandit() -> None:
    stage = _stage_with_options({"semgrep": {"enabled": True}, "bandit": {"enabled": True}})
    stage._run_semgrep = AsyncMock(return_value=[])
    stage._run_bandit = AsyncMock(return_value=[])
    action = make_action(file_path="/src/main.js", content="console.log('hi');\n")
    await stage.run(action)
    stage._run_semgrep.assert_called_once()
    stage._run_bandit.assert_not_called()


@pytest.mark.asyncio
async def test_semgrep_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    stage = SecurityStage(StageConfig(name="security", enabled=True, timeout=1, options={}))

    async def _raise(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr("detent.stages.security.asyncio.create_subprocess_exec", _raise)
    findings = await stage._run_semgrep("scan.py", "/src/main.py")
    assert findings[0].code == "semgrep/not-installed"
    assert findings[0].severity == "warning"


@pytest.mark.asyncio
async def test_bandit_not_installed(monkeypatch: pytest.MonkeyPatch) -> None:
    stage = SecurityStage(StageConfig(name="security", enabled=True, timeout=1, options={}))

    async def _raise(*_args: object, **_kwargs: object) -> None:
        raise FileNotFoundError

    monkeypatch.setattr("detent.stages.security.asyncio.create_subprocess_exec", _raise)
    findings = await stage._run_bandit("scan.py", "/src/main.py")
    assert findings[0].code == "bandit/not-installed"
    assert findings[0].severity == "warning"


@pytest.mark.asyncio
async def test_semgrep_parses_severity_and_code(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "results": [
            {
                "check_id": "S0001",
                "start": {"line": 1, "col": 2},
                "extra": {"message": "bad", "severity": "ERROR", "fix": "fix"},
            },
            {
                "check_id": "S0002",
                "start": {"line": 2, "col": 1},
                "extra": {"message": "warn", "severity": "INFO"},
            },
        ]
    }
    proc = FakeProc(returncode=1, stdout=json.dumps(payload).encode())

    async def _fake_exec(*_args: object, **_kwargs: object) -> FakeProc:
        return proc

    stage = SecurityStage(StageConfig(name="security", enabled=True, timeout=1, options={}))
    monkeypatch.setattr("detent.stages.security.asyncio.create_subprocess_exec", _fake_exec)
    findings = await stage._run_semgrep("scan.py", "/src/main.py")
    assert findings[0].severity == "error"
    assert findings[0].code == "semgrep/S0001"
    assert findings[1].severity == "warning"


@pytest.mark.asyncio
async def test_bandit_parses_severity_and_code(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "results": [
            {"test_id": "B101", "line_number": 3, "issue_text": "bad", "issue_severity": "HIGH"},
            {"test_id": "B201", "line_number": 4, "issue_text": "warn", "issue_severity": "MEDIUM"},
        ]
    }
    proc = FakeProc(returncode=1, stdout=json.dumps(payload).encode())

    async def _fake_exec(*_args: object, **_kwargs: object) -> FakeProc:
        return proc

    stage = SecurityStage(StageConfig(name="security", enabled=True, timeout=1, options={}))
    monkeypatch.setattr("detent.stages.security.asyncio.create_subprocess_exec", _fake_exec)
    findings = await stage._run_bandit("scan.py", "/src/main.py")
    assert findings[0].severity == "error"
    assert findings[0].code == "bandit/B101"
    assert findings[1].severity == "warning"


@pytest.mark.asyncio
async def test_deduplication_removes_duplicate() -> None:
    stage = _stage_with_options({"semgrep": {"enabled": True}, "bandit": {"enabled": True}})
    finding = stage._parse_bandit_result(
        {"test_id": "B101", "line_number": 3, "issue_text": "dup", "issue_severity": "HIGH"},
        "/src/main.py",
    )
    stage._run_semgrep = AsyncMock(return_value=[finding])
    stage._run_bandit = AsyncMock(return_value=[finding])
    action = make_action(file_path="/src/main.py", content="print('hi')\n")
    result = await stage.run(action)
    assert len(result.findings) == 1


@pytest.mark.asyncio
async def test_timeout_kills_process(monkeypatch: pytest.MonkeyPatch) -> None:
    proc = FakeProc(returncode=None, stdout=b"", stderr=b"")

    async def _fake_exec(*_args: object, **_kwargs: object) -> FakeProc:
        return proc

    async def _raise_timeout(awaitable: object, *_args: object, **_kwargs: object) -> tuple[bytes, bytes]:
        close = getattr(awaitable, "close", None)
        if callable(close):
            close()
        raise TimeoutError

    stage = SecurityStage(StageConfig(name="security", enabled=True, timeout=1, options={}))
    monkeypatch.setattr("detent.stages.security.asyncio.create_subprocess_exec", _fake_exec)
    monkeypatch.setattr("detent.stages.security.asyncio.wait_for", _raise_timeout)
    findings = await stage._run_semgrep("scan.py", "/src/main.py")
    assert proc.killed is True
    assert findings[0].code == "semgrep/timeout"


# ---- new tests for wiring -----------------------------------------------


@pytest.mark.asyncio
async def test_secrets_enabled_calls_secret_scan() -> None:
    from unittest.mock import AsyncMock, patch

    stage = _stage_with_options(
        {
            "semgrep": {"enabled": False},
            "bandit": {"enabled": False},
            "secrets": {"enabled": True},
            "dep_scan": {"enabled": False},
        }
    )
    with patch(
        "detent.stages.security.base.run_secret_scan",
        new=AsyncMock(return_value=[]),
    ) as mock_scan:
        action = make_action(file_path="/src/main.py", content="x = 1\n")
        result = await stage.run(action)
    mock_scan.assert_called_once()
    assert result.passed


@pytest.mark.asyncio
async def test_dep_scan_enabled_calls_dep_scan_for_manifest() -> None:
    from unittest.mock import AsyncMock, patch

    stage = _stage_with_options(
        {
            "semgrep": {"enabled": False},
            "bandit": {"enabled": False},
            "secrets": {"enabled": False},
            "dep_scan": {"enabled": True},
        }
    )
    with patch(
        "detent.stages.security.base.run_dep_scan",
        new=AsyncMock(return_value=[]),
    ) as mock_scan:
        action = make_action(file_path="requirements.txt", content="requests==2.31.0\n")
        await stage.run(action)
    mock_scan.assert_called_once()


@pytest.mark.asyncio
async def test_dep_scan_not_called_for_python_source() -> None:
    from unittest.mock import AsyncMock, patch

    stage = _stage_with_options(
        {
            "semgrep": {"enabled": False},
            "bandit": {"enabled": False},
            "secrets": {"enabled": False},
            "dep_scan": {"enabled": True},
        }
    )
    with patch(
        "detent.stages.security.base.run_dep_scan",
        new=AsyncMock(return_value=[]),
    ) as mock_scan:
        action = make_action(file_path="/src/main.py", content="x = 1\n")
        await stage.run(action)
    mock_scan.assert_not_called()


@pytest.mark.asyncio
async def test_metadata_tools_reflects_enabled_scanners() -> None:
    from unittest.mock import AsyncMock, patch

    stage = _stage_with_options(
        {
            "semgrep": {"enabled": False},
            "bandit": {"enabled": False},
            "secrets": {"enabled": True},
            "dep_scan": {"enabled": False},
        }
    )
    with patch(
        "detent.stages.security.base.run_secret_scan",
        new=AsyncMock(return_value=[]),
    ):
        action = make_action(file_path="/src/main.py", content="x = 1\n")
        result = await stage.run(action)
    assert "detect-secrets" in result.metadata["tools"]
