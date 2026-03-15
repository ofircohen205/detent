"""Unit tests for detent.stages.javascript — tsc (typecheck) helper."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from detent.stages.javascript import run_tsc


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
async def test_no_tsconfig_warns(tmp_path: Path) -> None:
    src = tmp_path / "file.ts"
    src.write_text("let x: number = 1;\n")
    result = await run_tsc(str(src), src.read_text(), stage_name="typecheck", timeout=1)
    assert result[0].code == "tsc/no-tsconfig"


@pytest.mark.asyncio
async def test_tsc_not_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "file.ts"
    src.write_text("let x: number = 1;\n")
    (tmp_path / "tsconfig.json").write_text("{}")

    async def _raise(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr("asyncio.create_subprocess_exec", _raise)
    result = await run_tsc(str(src), src.read_text(), stage_name="typecheck", timeout=1)
    assert result[0].code == "tsc/not-installed"


@pytest.mark.asyncio
async def test_parses_tsc_errors(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    src = tmp_path / "file.ts"
    src.write_text("let x: number = 'hi';\n")
    (tmp_path / "tsconfig.json").write_text("{}")

    stdout = b"/src/file.ts(1,5): error TS2322: Type 'string' is not assignable to type 'number'.\n"

    async def _fake_exec(*args, **kwargs):
        return FakeProc(returncode=1, stdout=stdout)

    monkeypatch.setattr("asyncio.create_subprocess_exec", _fake_exec)
    result = await run_tsc(str(src), src.read_text(), stage_name="typecheck", timeout=1)
    assert result[0].code == "tsc/TS2322"
    assert result[0].severity == "error"
