"""Tests for LiteLLM adapter."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from detent.adapters.hook.litellm import LiteLLMAdapter


@pytest.mark.asyncio
async def test_litellm_adapter_observes_without_intercepting():
    """LiteLLMAdapter should call pipeline.run and not intercept_tool_call."""
    session_manager = MagicMock()
    session_manager.pipeline.run = AsyncMock(return_value=MagicMock(passed=True))
    session_manager.ipc_channel.send_message = AsyncMock()
    session_manager.intercept_tool_call = AsyncMock()

    adapter = LiteLLMAdapter(session_manager=session_manager)
    raw_event = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/x.py", "content": "x = 1"},
        "tool_call_id": "call_1",
        "session_id": "sess_1",
    }

    await adapter.handle_event(raw_event)

    session_manager.pipeline.run.assert_called_once()
    session_manager.intercept_tool_call.assert_not_called()
