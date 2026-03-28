# tests/unit/stages/test_secret_scan.py
"""Unit tests for secret scanning sub-stage (_secrets.py)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from detent.stages.security._secrets import run_secret_scan


class FakeProc:
    def __init__(self, *, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        pass


def _secrets_output(hits: list[dict[str, object]], tmp_path: str = "/tmp/f.py") -> bytes:
    return json.dumps({"version": "1.5.0", "results": {tmp_path: hits}}).encode()


@pytest.mark.asyncio
async def test_no_secrets_returns_empty() -> None:
    empty = json.dumps({"version": "1.5.0", "results": {}}).encode()
    proc = FakeProc(returncode=0, stdout=empty)
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        result = await run_secret_scan("x = 1\n", "/src/main.py", "security", 30)
    assert result == []


@pytest.mark.asyncio
async def test_detects_secret_returns_error_finding() -> None:
    hits = [{"type": "AWS Access Key", "line_number": 5, "hashed_secret": "abc"}]
    proc = FakeProc(returncode=0, stdout=_secrets_output(hits))
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        result = await run_secret_scan("KEY='AKIA...'\n", "/src/config.py", "security", 30)
    assert len(result) == 1
    assert result[0].severity == "error"
    assert result[0].line == 5
    assert "AWS Access Key" in result[0].message
    assert result[0].code == "secrets/aws-access-key"
    assert result[0].fix_suggestion is not None


@pytest.mark.asyncio
async def test_multiple_secrets_returns_multiple_findings() -> None:
    hits = [
        {"type": "Secret Keyword", "line_number": 2, "hashed_secret": "h1"},
        {"type": "Basic Auth Credentials", "line_number": 7, "hashed_secret": "h2"},
    ]
    proc = FakeProc(returncode=0, stdout=_secrets_output(hits))
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        result = await run_secret_scan("content", "/src/auth.py", "security", 30)
    assert len(result) == 2
    assert all(f.severity == "error" for f in result)


@pytest.mark.asyncio
async def test_not_installed_returns_warning() -> None:
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        result = await run_secret_scan("x = 1\n", "/src/main.py", "security", 30)
    assert len(result) == 1
    assert result[0].severity == "warning"
    assert result[0].code == "secrets/not-installed"
    assert "detect-secrets" in result[0].message


@pytest.mark.asyncio
async def test_nonzero_exit_returns_warning() -> None:
    proc = FakeProc(returncode=2, stdout=b"", stderr=b"internal error")
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        result = await run_secret_scan("x = 1\n", "/src/main.py", "security", 30)
    assert len(result) == 1
    assert result[0].severity == "warning"
    assert result[0].code == "secrets/error"


@pytest.mark.asyncio
async def test_invalid_json_returns_warning() -> None:
    proc = FakeProc(returncode=0, stdout=b"not json {")
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        result = await run_secret_scan("x = 1\n", "/src/main.py", "security", 30)
    assert len(result) == 1
    assert result[0].severity == "warning"
    assert result[0].code == "secrets/error"


@pytest.mark.asyncio
async def test_finding_file_is_original_path_not_tmp() -> None:
    hits = [{"type": "Secret Keyword", "line_number": 1, "hashed_secret": "h"}]
    proc = FakeProc(returncode=0, stdout=_secrets_output(hits))
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        result = await run_secret_scan("pass=secret\n", "/src/real.py", "security", 30)
    assert result[0].file == "/src/real.py"
