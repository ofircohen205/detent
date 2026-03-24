"""Tests for hook adapter exception safety."""

import json
from unittest.mock import AsyncMock

import pytest

from detent.adapters.hook.base import HookAdapter
from detent.schema import ActionType, AgentAction, RiskLevel


class _TestHookAdapter(HookAdapter):
    @property
    def agent_name(self) -> str:
        return "test-hook"

    @property
    def route(self) -> str:
        return "/hooks/test"

    async def intercept(self, raw_event: dict[str, object]) -> AgentAction | None:
        return AgentAction(
            action_type=ActionType.FILE_WRITE,
            agent=self.agent_name,
            tool_name="Write",
            tool_input={"file_path": "/tmp/test.py", "content": "print('hi')"},
            tool_call_id="toolu_test",
            session_id="sess_test",
            checkpoint_ref="",
            risk_level=RiskLevel.MEDIUM,
        )


@pytest.mark.asyncio
async def test_hook_handler_returns_200_when_intercept_tool_call_raises():
    session_manager = AsyncMock()
    session_manager.intercept_tool_call.side_effect = RuntimeError("boom")
    adapter = _TestHookAdapter(session_manager=session_manager)
    request = AsyncMock()
    request.json.return_value = {"tool_name": "Write"}

    response = await adapter._hook_handler(request)

    assert response.status == 200
    assert json.loads(response.text) == {"status": "error", "detail": "Detent internal error"}


@pytest.mark.asyncio
async def test_hook_handler_returns_200_when_result_handler_raises():
    session_manager = AsyncMock()
    session_manager.intercept_tool_call.return_value = AsyncMock()
    adapter = _TestHookAdapter(session_manager=session_manager)
    adapter.handle_verification_result = AsyncMock(side_effect=RuntimeError("boom"))  # type: ignore[method-assign]
    request = AsyncMock()
    request.json.return_value = {"tool_name": "Write"}

    response = await adapter._hook_handler(request)

    assert response.status == 200
    assert json.loads(response.text) == {"status": "error", "detail": "Detent internal error"}
