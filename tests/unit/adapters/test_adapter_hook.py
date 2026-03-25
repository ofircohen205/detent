"""Tests for hook adapters."""

from unittest.mock import MagicMock

import pytest
from aiohttp import web

from detent.adapters.hook import HookAdapter
from detent.adapters.hook.gemini import GeminiAdapter
from detent.schema import ActionType


class DummyHookAdapter(HookAdapter):
    @property
    def agent_name(self) -> str:
        return "dummy"

    @property
    def route(self) -> str:
        return "/hooks/dummy"

    async def intercept(self, raw_event: dict):
        return None


def test_hook_adapter_lifecycle_active_flag():
    """HookAdapter should toggle _active on register/unregister."""
    app = web.Application()
    adapter = DummyHookAdapter(session_manager=MagicMock())
    assert adapter._active is False
    adapter.register(app)
    assert adapter._active is True
    adapter.unregister(app)
    assert adapter._active is False


@pytest.mark.asyncio
async def test_gemini_adapter_intercept():
    """GeminiAdapter should parse Gemini CLI BeforeTool payloads."""
    adapter = GeminiAdapter(session_manager=MagicMock())
    raw_event = {"tool_name": "Write", "tool_input": {"file_path": "/tmp/x.py", "content": "x = 1"}}
    action = await adapter.intercept(raw_event)
    assert action is not None
    assert action.action_type == ActionType.FILE_WRITE


@pytest.mark.asyncio
async def test_gemini_adapter_intercept_with_mcp_context():
    """GeminiAdapter should ignore optional mcp_context while parsing tool input."""
    adapter = GeminiAdapter(session_manager=MagicMock())
    raw_event = {
        "tool_name": "Write",
        "tool_input": {"file_path": "/tmp/x.py", "content": "x = 1"},
        "mcp_context": {"server": "filesystem"},
    }
    action = await adapter.intercept(raw_event)
    assert action is not None
    assert action.action_type == ActionType.FILE_WRITE


@pytest.mark.asyncio
async def test_gemini_adapter_function_call_fallback():
    """GeminiAdapter should retain compatibility with legacy functionCall payloads."""
    adapter = GeminiAdapter(session_manager=MagicMock())
    raw_event = {"functionCall": {"name": "Write", "args": {"file_path": "/tmp/x.py", "content": "x = 1"}}}
    action = await adapter.intercept(raw_event)
    assert action is not None
    assert action.action_type == ActionType.FILE_WRITE
