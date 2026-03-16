"""Unit tests for AgentAdapter base class."""

from unittest.mock import MagicMock

import pytest

from detent.adapters.base import AgentAdapter
from detent.schema import ActionType, AgentAction


class MockAdapter(AgentAdapter):
    """Mock adapter for testing base class functionality."""

    @property
    def agent_name(self) -> str:
        """Return the adapter name."""
        return "test-agent"

    async def intercept(self, raw_event: dict) -> AgentAction | None:
        """Normalize raw event to AgentAction."""
        return AgentAction(
            action_type="file_write",
            agent=self.agent_name,
            tool_name=raw_event["tool"],
            tool_input=raw_event["input"],
            tool_call_id=raw_event["id"],
            session_id="sess_test",
            checkpoint_ref="chk_test",
            risk_level="medium",
        )


def test_adapter_base_abstract():
    """AgentAdapter should be abstract and require implementation."""
    mock_session_manager = MagicMock()
    with pytest.raises(TypeError):
        AgentAdapter(session_manager=mock_session_manager)  # Should fail: abstract class


def test_adapter_agent_name_is_abstract():
    """Concrete adapter must implement agent_name property."""
    mock_session_manager = MagicMock()
    adapter = MockAdapter(session_manager=mock_session_manager)
    assert adapter.agent_name == "test-agent"


@pytest.mark.asyncio
async def test_mock_adapter_intercept():
    """Mock adapter should normalize raw event to AgentAction."""
    mock_session_manager = MagicMock()
    adapter = MockAdapter(session_manager=mock_session_manager)
    raw_event = {
        "tool": "Write",
        "input": {"file_path": "/src/main.py", "content": "x = 1"},
        "id": "call_123",
    }
    action = await adapter.intercept(raw_event)
    assert action.tool_name == "Write"
    assert action.tool_input["file_path"] == "/src/main.py"


def test_action_type_map_shared():
    """_ACTION_TYPE_MAP should include core tool mappings."""
    assert AgentAdapter._ACTION_TYPE_MAP["Write"] == ActionType.FILE_WRITE
    assert AgentAdapter._ACTION_TYPE_MAP["Bash"] == ActionType.SHELL_EXEC
