"""Unit tests for detent.stages.javascript — Jest/Vitest (tests) helper."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from detent.stages.javascript import run_jest


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
async def test_no_runner_warns(tmp_path: Path) -> None:
    src = tmp_path / "file.ts"
    src.write_text("console.log('x');\n")
    result = await run_jest(str(src), stage_name="tests", timeout=1, tool_override=None)
    assert result[0].code == "testsjs/no-runner"


@pytest.mark.asyncio
async def test_no_test_file_returns_empty(tmp_path: Path) -> None:
    src = tmp_path / "file.ts"
    src.write_text("console.log('x');\n")
    package = tmp_path / "package.json"
    package.write_text(json.dumps({"devDependencies": {"jest": "^29.0.0"}}))
    result = await run_jest(str(src), stage_name="tests", timeout=1, tool_override=None)
    assert result == []


@pytest.mark.asyncio
async def test_jest_failure_parsed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "file.ts"
    src.write_text("console.log('x');\n")
    package = tmp_path / "package.json"
    package.write_text(json.dumps({"devDependencies": {"jest": "^29.0.0"}}))
    test_file = tmp_path / "file.test.ts"
    test_file.write_text("test('fail', () => expect(true).toBe(false));\n")

    payload = json.dumps(
        {
            "testResults": [
                {
                    "assertionResults": [
                        {
                            "status": "failed",
                            "fullName": "suite fail",
                            "title": "fail",
                            "failureMessages": ["bad"],
                            "location": {"line": 10},
                        }
                    ]
                }
            ]
        }
    ).encode("utf-8")

    async def _fake_exec(*args, **kwargs):
        return FakeProc(returncode=1, stdout=payload)

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    result = await run_jest(str(src), stage_name="tests", timeout=1, tool_override=None)
    assert len(result) == 1
    assert result[0].code == "jest/assertion-failed"
    assert result[0].line == 10
