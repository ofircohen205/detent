"""Shared pytest fixtures for Detent test suite."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from detent.schema import ActionType, AgentAction, RiskLevel


class FakeProc:
    """Minimal asyncio.subprocess.Process stand-in for unit tests."""

    def __init__(self, *, returncode: int = 0, stdout: bytes = b"", stderr: bytes = b"") -> None:
        self.returncode = returncode
        self._stdout = stdout
        self._stderr = stderr

    async def communicate(self) -> tuple[bytes, bytes]:
        return self._stdout, self._stderr

    def kill(self) -> None:
        pass


@pytest.fixture
def sample_action() -> AgentAction:
    """Create a sample AgentAction for file_write testing."""
    return AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="claude-code",
        tool_name="Write",
        tool_input={
            "file_path": "/src/main.py",
            "content": 'def hello():\n    print("Hello, world!")\n',
        },
        tool_call_id="toolu_01ABC123",
        session_id="sess_test_001",
        checkpoint_ref="chk_before_write_001",
        risk_level=RiskLevel.MEDIUM,
    )


@pytest.fixture
def sample_action_bad_syntax() -> AgentAction:
    """Create a sample AgentAction with Python syntax errors."""
    return AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="claude-code",
        tool_name="Write",
        tool_input={
            "file_path": "/src/broken.py",
            "content": "def hello(\n    print('missing paren')\n",
        },
        tool_call_id="toolu_01DEF456",
        session_id="sess_test_001",
        checkpoint_ref="chk_before_write_002",
        risk_level=RiskLevel.MEDIUM,
    )


@pytest.fixture
def tmp_project_dir(tmp_path: Path) -> Path:
    """Create a temporary project directory with basic structure."""
    # Create basic project structure
    src_dir = tmp_path / "src"
    src_dir.mkdir()

    # Write a simple Python file
    main_py = src_dir / "main.py"
    main_py.write_text('def hello():\n    print("Hello, world!")\n')

    # Write a test file
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()

    test_main = tests_dir / "test_main.py"
    test_main.write_text(
        "from src.main import hello\n\ndef test_hello(capsys):\n    hello()\n    assert capsys.readouterr().out == 'Hello, world!\\n'\n"
    )

    return tmp_path


def make_action(
    *,
    file_path: str = "/src/main.py",
    content: str = 'print("hello")\n',
    action_type: ActionType = ActionType.FILE_WRITE,
    agent: str = "claude-code",
    tool_name: str = "Write",
    checkpoint_ref: str = "chk_test_001",
    **kwargs: Any,
) -> AgentAction:
    """Factory helper to create AgentAction instances with minimal boilerplate."""
    return AgentAction(
        action_type=action_type,
        agent=agent,
        tool_name=tool_name,
        tool_input={"file_path": file_path, "content": content},
        tool_call_id=kwargs.get("tool_call_id", "toolu_test"),
        session_id=kwargs.get("session_id", "sess_test"),
        checkpoint_ref=checkpoint_ref,
        risk_level=kwargs.get("risk_level", RiskLevel.MEDIUM),
    )
