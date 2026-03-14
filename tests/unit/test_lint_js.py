"""Unit tests for detent.stages.lint_js."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from detent.stages.lint_js import run_eslint


class FakeProc:
    def __init__(self, returncode: int, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        self.returncode = 2


async def _fake_wait_for(coro, timeout):  # type: ignore[no-untyped-def]
    return await coro


@pytest.fixture(autouse=True)
def patch_wait_for(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(asyncio, "wait_for", _fake_wait_for)


@pytest.mark.asyncio
async def test_no_config_warns(tmp_path: Path) -> None:
    src = tmp_path / "file.js"
    src.write_text("console.log('hello');\n")
    result = await run_eslint(str(src), src.read_text(), timeout=1)
    assert len(result) == 1
    assert "No ESLint config found" in result[0].message


@pytest.mark.asyncio
async def test_missing_eslint_tool(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "file.js"
    src.write_text("console.log('hi');\n")
    (tmp_path / "eslint.config.js").write_text("")

    async def _raise(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("asyncio.create_subprocess_exec", _raise)
    result = await run_eslint(str(src), src.read_text(), timeout=1)
    assert result[0].code == "eslint/not-installed"


@pytest.mark.asyncio
async def test_parses_findings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "file.js"
    src.write_text("alert('x');\n")
    (tmp_path / "eslint.config.js").write_text("")

    output = json.dumps(
        [
            {
                "messages": [
                    {
                        "line": 1,
                        "column": 1,
                        "message": "Unexpected console statement",
                        "ruleId": "no-console",
                        "severity": 2,
                    }
                ]
            }
        ]
    ).encode("utf-8")

    async def _fake_exec(*args, **kwargs):
        return FakeProc(returncode=1, stdout=output)

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    result = await run_eslint(str(src), src.read_text(), timeout=1)
    assert len(result) == 1
    assert result[0].severity == "error"
    assert result[0].code == "eslint/no-console"
