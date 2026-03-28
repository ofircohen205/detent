# tests/unit/stages/test_dep_scan.py
"""Unit tests for dependency scanning sub-stage (_dep_scan.py)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest

from detent.stages.security._dep_scan import is_dependency_manifest, run_dep_scan


class FakeProc:
    def __init__(self, *, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        pass


# ---- is_dependency_manifest -------------------------------------------------


def test_requirements_txt_is_manifest() -> None:
    assert is_dependency_manifest("/project/requirements.txt") is True


def test_requirements_dev_txt_is_manifest() -> None:
    assert is_dependency_manifest("/project/requirements-dev.txt") is True


def test_requirements_test_txt_is_manifest() -> None:
    assert is_dependency_manifest("requirements-test.txt") is True


def test_arbitrary_requirements_txt_is_manifest() -> None:
    assert is_dependency_manifest("requirements-prod.txt") is True


def test_python_source_is_not_manifest() -> None:
    assert is_dependency_manifest("/src/main.py") is False


def test_package_json_is_not_manifest() -> None:
    assert is_dependency_manifest("package.json") is False


def test_setup_py_is_not_manifest() -> None:
    assert is_dependency_manifest("setup.py") is False


# ---- run_dep_scan -----------------------------------------------------------


def _vuln_output(name: str = "requests", version: str = "2.25.0") -> bytes:
    return json.dumps(
        {
            "dependencies": [
                {
                    "name": name,
                    "version": version,
                    "vulns": [
                        {
                            "id": "PYSEC-2023-74",
                            "description": "Unintended leak via proxies",
                            "aliases": ["CVE-2023-32681"],
                            "fix_versions": ["2.31.0"],
                        }
                    ],
                }
            ],
            "fixes": [],
        }
    ).encode()


def _clean_output() -> bytes:
    return json.dumps({"dependencies": [{"name": "requests", "version": "2.31.0", "vulns": []}], "fixes": []}).encode()


@pytest.mark.asyncio
async def test_non_manifest_returns_empty() -> None:
    result = await run_dep_scan("x = 1\n", "/src/main.py", "security", 30)
    assert result == []


@pytest.mark.asyncio
async def test_clean_requirements_returns_empty() -> None:
    proc = FakeProc(returncode=0, stdout=_clean_output())
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        result = await run_dep_scan("requests==2.31.0\n", "requirements.txt", "security", 30)
    assert result == []


@pytest.mark.asyncio
async def test_vulnerable_package_returns_error_finding() -> None:
    proc = FakeProc(returncode=1, stdout=_vuln_output())
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        result = await run_dep_scan("requests==2.25.0\n", "requirements.txt", "security", 30)
    assert len(result) == 1
    assert result[0].severity == "error"
    assert "requests" in result[0].message
    assert "2.25.0" in result[0].message
    assert result[0].code == "dep-scan/PYSEC-2023-74"
    assert result[0].fix_suggestion == "Upgrade to 2.31.0"


@pytest.mark.asyncio
async def test_no_fix_available_shows_fallback_message() -> None:
    output = json.dumps(
        {
            "dependencies": [
                {
                    "name": "old-pkg",
                    "version": "0.1.0",
                    "vulns": [{"id": "CVE-X", "description": "bad", "aliases": [], "fix_versions": []}],
                }
            ],
            "fixes": [],
        }
    ).encode()
    proc = FakeProc(returncode=1, stdout=output)
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        result = await run_dep_scan("old-pkg==0.1.0\n", "requirements.txt", "security", 30)
    assert result[0].fix_suggestion is not None
    assert "No fix" in result[0].fix_suggestion


@pytest.mark.asyncio
async def test_not_installed_returns_warning() -> None:
    with patch("asyncio.create_subprocess_exec", side_effect=FileNotFoundError):
        result = await run_dep_scan("requests==2.25.0\n", "requirements.txt", "security", 30)
    assert len(result) == 1
    assert result[0].severity == "warning"
    assert result[0].code == "dep-scan/not-installed"
    assert "pip-audit" in result[0].message


@pytest.mark.asyncio
async def test_error_exit_code_returns_warning() -> None:
    proc = FakeProc(returncode=2, stdout=b"", stderr=b"resolution failed")
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        result = await run_dep_scan("requests==2.25.0\n", "requirements.txt", "security", 30)
    assert len(result) == 1
    assert result[0].severity == "warning"
    assert result[0].code == "dep-scan/error"


@pytest.mark.asyncio
async def test_invalid_json_returns_warning() -> None:
    proc = FakeProc(returncode=0, stdout=b"bad json {")
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        result = await run_dep_scan("requests==2.31.0\n", "requirements.txt", "security", 30)
    assert len(result) == 1
    assert result[0].severity == "warning"
    assert result[0].code == "dep-scan/error"


@pytest.mark.asyncio
async def test_finding_file_is_original_path() -> None:
    proc = FakeProc(returncode=1, stdout=_vuln_output())
    with patch("asyncio.create_subprocess_exec", new=AsyncMock(return_value=proc)):
        result = await run_dep_scan("requests==2.25.0\n", "/project/requirements.txt", "security", 30)
    assert result[0].file == "/project/requirements.txt"
