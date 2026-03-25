"""Tests for HTTP proxy observational response handling."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from detent.proxy.http_proxy import DetentProxy
from detent.schema import ActionType, AgentAction, RiskLevel


def _file_write_action() -> AgentAction:
    return AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": "/tmp/test.py", "content": "print('hi')"},
        tool_call_id="toolu_123",
        session_id="",
        checkpoint_ref="",
        risk_level=RiskLevel.MEDIUM,
    )


@pytest.mark.asyncio
async def test_observe_response_calls_adapter_and_session_manager():
    session_manager = MagicMock()
    session_manager.is_active = True
    session_manager.session_id = "sess_123"
    session_manager.observe_tool_call = AsyncMock()

    action = _file_write_action()
    http_adapter = MagicMock()
    http_adapter.intercept_response = AsyncMock(return_value=[action])

    proxy = DetentProxy(session_manager=session_manager, http_adapter=http_adapter)

    await proxy._observe_response(b"{}")

    http_adapter.intercept_response.assert_awaited_once_with(b"{}")
    session_manager.observe_tool_call.assert_awaited_once_with(action)
    assert action.session_id == "sess_123"


@pytest.mark.asyncio
async def test_observe_response_skips_when_session_inactive():
    session_manager = MagicMock()
    session_manager.is_active = False
    session_manager.session_id = None
    session_manager.observe_tool_call = AsyncMock()

    http_adapter = MagicMock()
    http_adapter.intercept_response = AsyncMock(return_value=[_file_write_action()])

    proxy = DetentProxy(session_manager=session_manager, http_adapter=http_adapter)

    await proxy._observe_response(b"{}")

    session_manager.observe_tool_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_observe_response_swallows_adapter_exceptions():
    session_manager = MagicMock()
    session_manager.is_active = True
    session_manager.session_id = "sess_123"
    session_manager.observe_tool_call = AsyncMock()

    http_adapter = MagicMock()
    http_adapter.intercept_response = AsyncMock(side_effect=RuntimeError("boom"))

    proxy = DetentProxy(session_manager=session_manager, http_adapter=http_adapter)

    await proxy._observe_response(b"{}")

    session_manager.observe_tool_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_observe_response_returns_when_http_adapter_missing():
    session_manager = MagicMock()
    session_manager.is_active = True
    session_manager.session_id = "sess_123"
    session_manager.observe_tool_call = AsyncMock()

    proxy = DetentProxy(session_manager=session_manager, http_adapter=None)

    await proxy._observe_response(b"{}")

    session_manager.observe_tool_call.assert_not_awaited()
