# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Detent Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest.mock import MagicMock

import pytest

from detent.adapters.base import AgentAdapter
from detent.proxy.session import SessionManager
from detent.schema import ActionType, AgentAction, RiskLevel


@pytest.fixture
def mock_session_manager():
    """Create a mock SessionManager."""
    return MagicMock(spec=SessionManager)


@pytest.fixture
def adapter(mock_session_manager):
    """Create a concrete AgentAdapter subclass for testing."""

    class TestAdapter(AgentAdapter):
        @property
        def agent_name(self) -> str:
            return "test-adapter"

        async def intercept(self, raw_event):
            return None

    return TestAdapter(mock_session_manager)


def test_log_intercept_start(adapter, capsys):
    """Test _log_intercept_start logs at DEBUG level."""
    adapter._log_intercept_start("tool_call")
    captured = capsys.readouterr()

    assert "intercepting tool_call" in captured.out
    assert "test-adapter" in captured.out
    assert "[debug" in captured.out


def test_log_intercept_end_with_action(adapter, capsys):
    """Test _log_intercept_end logs action details."""
    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="test-adapter",
        tool_name="Write",
        tool_input={"file_path": "src/main.py"},
        tool_call_id="abc123",
        session_id="sess_001",
        checkpoint_ref="chk_001",
        risk_level=RiskLevel.MEDIUM,
    )
    adapter._log_intercept_end(action)
    captured = capsys.readouterr()

    assert "action created" in captured.out
    assert "Write" in captured.out
    assert "abc123" in captured.out
    assert "file_write" in captured.out


def test_log_intercept_end_with_none(adapter, capsys):
    """Test _log_intercept_end logs when action is None."""
    adapter._log_intercept_end(None)
    captured = capsys.readouterr()

    assert "action skipped" in captured.out
    assert "test-adapter" in captured.out


def test_log_intercept_error(adapter, capsys):
    """Test _log_intercept_error logs at WARNING level."""
    adapter._log_intercept_error("missing_field", "tool_name required")
    captured = capsys.readouterr()

    assert "intercept error" in captured.out
    assert "missing_field" in captured.out
    assert "tool_name required" in captured.out
    assert "[warning" in captured.out


def test_log_result_handling_start(adapter, capsys):
    """Test _log_result_handling_start logs at DEBUG level."""
    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="test-adapter",
        tool_name="Write",
        tool_input={"file_path": "src/main.py"},
        tool_call_id="abc123",
        session_id="sess_001",
        checkpoint_ref="chk_001",
        risk_level=RiskLevel.MEDIUM,
    )
    adapter._log_result_handling_start(action)
    captured = capsys.readouterr()

    assert "handling verification result" in captured.out
    assert "Write" in captured.out


def test_log_result_handling_end_allowed(adapter, capsys):
    """Test _log_result_handling_end logs INFO when allowed."""
    adapter._log_result_handling_end(action_allowed=True)
    captured = capsys.readouterr()

    assert "allowing execution" in captured.out
    assert "[info" in captured.out


def test_log_result_handling_end_denied(adapter, capsys):
    """Test _log_result_handling_end logs INFO when denied."""
    adapter._log_result_handling_end(action_allowed=False)
    captured = capsys.readouterr()

    assert "denying execution" in captured.out
    assert "[info" in captured.out


def test_log_performance(adapter, capsys):
    """Test _log_performance logs execution time."""
    adapter._log_performance("intercept", 2.5)
    captured = capsys.readouterr()

    assert "intercept completed in 2.5ms" in captured.out
    assert "[debug" in captured.out
