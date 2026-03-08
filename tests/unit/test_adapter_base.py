"""Unit tests for AgentAdapter base class."""

from unittest.mock import MagicMock

import pytest

from detent.adapters.base import AgentAdapter
from detent.schema import AgentAction


class MockAdapter(AgentAdapter):
    """Mock adapter for testing base class functionality."""

    agent_name = "test-agent"

    async def intercept(self, raw_event: dict) -> AgentAction:
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
    """AgentAdapter should be abstract and require agent_name."""
    mock_session_manager = MagicMock()
    with pytest.raises(TypeError):
        AgentAdapter(session_manager=mock_session_manager)  # Should fail: abstract class


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
