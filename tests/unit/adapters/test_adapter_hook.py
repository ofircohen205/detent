"""Tests for hook adapters."""

from unittest.mock import MagicMock

import pytest
from aiohttp import web

from detent.adapters.hook import HookAdapter
from detent.adapters.hook.gemini import GeminiAdapter
from detent.config.languages import is_verifiable_file
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
    """GeminiAdapter should parse Gemini CLI BeforeTool payloads with native tool names."""
    adapter = GeminiAdapter(session_manager=MagicMock())
    raw_event = {"tool_name": "write_file", "tool_input": {"file_path": "/tmp/x.py", "content": "x = 1"}}
    action = await adapter.intercept(raw_event)
    assert action is not None
    assert action.action_type == ActionType.FILE_WRITE


@pytest.mark.asyncio
async def test_gemini_adapter_intercept_with_mcp_context():
    """GeminiAdapter should ignore optional mcp_context while parsing tool input."""
    adapter = GeminiAdapter(session_manager=MagicMock())
    raw_event = {
        "tool_name": "write_file",
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
    raw_event = {"functionCall": {"name": "write_file", "args": {"file_path": "/tmp/x.py", "content": "x = 1"}}}
    action = await adapter.intercept(raw_event)
    assert action is not None
    assert action.action_type == ActionType.FILE_WRITE


@pytest.mark.asyncio
async def test_gemini_adapter_write_file_native_tool():
    """GeminiAdapter maps Gemini-native 'write_file' to FILE_WRITE."""
    adapter = GeminiAdapter(session_manager=MagicMock())
    action = await adapter.intercept(
        {
            "tool_name": "write_file",
            "tool_input": {"file_path": "/src/main.py", "content": "x = 1"},
        }
    )
    assert action is not None
    assert action.action_type == ActionType.FILE_WRITE
    assert action.tool_name == "write_file"


@pytest.mark.asyncio
async def test_gemini_adapter_edit_native_tool():
    """GeminiAdapter maps Gemini-native 'edit' to FILE_WRITE."""
    adapter = GeminiAdapter(session_manager=MagicMock())
    action = await adapter.intercept(
        {
            "tool_name": "edit",
            "tool_input": {"file_path": "/src/main.py", "old_string": "x", "new_string": "y"},
        }
    )
    assert action is not None
    assert action.action_type == ActionType.FILE_WRITE


@pytest.mark.asyncio
async def test_gemini_adapter_read_file_returns_none():
    """GeminiAdapter skips 'read_file' — not a file write."""
    adapter = GeminiAdapter(session_manager=MagicMock())
    action = await adapter.intercept({"tool_name": "read_file", "tool_input": {"file_path": "/src/main.py"}})
    assert action is None


@pytest.mark.asyncio
async def test_gemini_adapter_web_search_returns_none():
    """GeminiAdapter skips 'google_web_search' — not a file write."""
    adapter = GeminiAdapter(session_manager=MagicMock())
    action = await adapter.intercept({"tool_name": "google_web_search", "tool_input": {"query": "python docs"}})
    assert action is None


@pytest.mark.asyncio
async def test_gemini_adapter_missing_tool_name_returns_none():
    """GeminiAdapter returns None on missing tool_name (consistent with other adapters)."""
    adapter = GeminiAdapter(session_manager=MagicMock())
    action = await adapter.intercept({"tool_input": {"file_path": "/tmp/x.py"}})
    assert action is None


@pytest.mark.asyncio
async def test_gemini_write_file_not_recognized_by_claude_code_adapter():
    """Gemini-native 'write_file' is NOT in ClaudeCodeHookAdapter's map — verifies namespace isolation."""
    from detent.adapters.hook.claude_code import ClaudeCodeHookAdapter

    adapter = ClaudeCodeHookAdapter(session_manager=MagicMock())
    action = await adapter.intercept(
        {
            "hook_event_name": "PreToolUse",
            "tool_name": "write_file",
            "tool_input": {"file_path": "/src/main.py", "content": "x=1"},
            "tool_call_id": "t1",
        }
    )
    assert action is None


@pytest.mark.asyncio
async def test_gemini_adapter_http_skipped_for_non_write(aiohttp_client):
    """HTTP handler returns {status: skipped} when Gemini intercept returns None."""
    adapter = GeminiAdapter(session_manager=MagicMock())
    app = web.Application()
    adapter.register(app)
    client = await aiohttp_client(app)

    resp = await client.post(
        "/hooks/gemini",
        json={"tool_name": "read_file", "tool_input": {"file_path": "/src/main.py"}},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body == {"status": "skipped"}


# ---- Extension guard (is_verifiable_file) ------------------------------------


@pytest.mark.parametrize(
    "file_path",
    [
        "/src/main.py",
        "/app/utils.js",
        "/app/component.tsx",
        "/lib/server.go",
        "/lib/parser.rs",
        "/project/requirements.txt",
        "/project/requirements-dev.txt",
        "/project/pyproject.toml",
        "/project/package.json",
        "/project/go.mod",
        "/project/Cargo.toml",
    ],
)
def test_verifiable_file_passes(file_path: str) -> None:
    """Code files and dependency manifests should pass the extension guard."""
    assert is_verifiable_file(file_path) is True


@pytest.mark.parametrize(
    "file_path",
    [
        "/docs/README.md",
        "/config/settings.yaml",
        "/data/output.json",
        "/assets/logo.png",
        "/project/setup.txt",  # not a requirements-family name
        "/project/notes.txt",
    ],
)
def test_non_verifiable_file_skipped(file_path: str) -> None:
    """Non-code, non-manifest files should be filtered by the extension guard."""
    assert is_verifiable_file(file_path) is False


@pytest.mark.asyncio
async def test_hook_skips_unsupported_extension(aiohttp_client) -> None:
    """HTTP handler returns {status: skipped} for files with unsupported extensions."""

    session_manager = MagicMock()
    adapter = GeminiAdapter(session_manager=session_manager)
    app = web.Application()
    adapter.register(app)
    client = await aiohttp_client(app)

    resp = await client.post(
        "/hooks/gemini",
        json={"tool_name": "write_file", "tool_input": {"file_path": "/docs/notes.md", "content": "hello"}},
    )
    assert resp.status == 200
    body = await resp.json()
    assert body == {"status": "skipped"}
    session_manager.intercept_tool_call.assert_not_called()


@pytest.mark.asyncio
async def test_hook_allows_requirements_txt(aiohttp_client) -> None:
    """HTTP handler does NOT skip requirements.txt (dependency manifest)."""
    from unittest.mock import AsyncMock

    from detent.pipeline.result import VerificationResult

    mock_result = VerificationResult(stage="security", passed=True, findings=[], duration_ms=1.0)
    session_manager = MagicMock()
    session_manager.intercept_tool_call = AsyncMock(return_value=mock_result)

    adapter = GeminiAdapter(session_manager=session_manager)
    app = web.Application()
    adapter.register(app)
    client = await aiohttp_client(app)

    resp = await client.post(
        "/hooks/gemini",
        json={
            "tool_name": "write_file",
            "tool_input": {"file_path": "/project/requirements.txt", "content": "requests==2.31.0\n"},
        },
    )
    assert resp.status == 200
    body = await resp.json()
    # Not skipped — went through to intercept_tool_call
    assert body.get("status") != "skipped"
    session_manager.intercept_tool_call.assert_called_once()
