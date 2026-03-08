"""Tests for HTTP reverse proxy."""

import json

import aiohttp
import pytest
from aiohttp import web

from detent.proxy.http_proxy import DetentProxy


@pytest.mark.asyncio
async def test_proxy_starts_and_stops():
    """Proxy should start on configured port and stop cleanly."""
    proxy = DetentProxy(port=9999, upstream_url="https://api.anthropic.com")
    await proxy.start()
    assert proxy.is_running is True
    await proxy.stop()
    assert proxy.is_running is False


@pytest.mark.asyncio
async def test_proxy_health_endpoint():
    """GET /health should return status and session_id."""
    proxy = DetentProxy(port=9998, upstream_url="https://api.anthropic.com")
    await proxy.start()

    try:
        async with aiohttp.ClientSession() as session, session.get(f"http://127.0.0.1:{proxy.port}/health") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
            assert "session_id" in data
    finally:
        await proxy.stop()


@pytest.mark.asyncio
async def test_proxy_forwards_request_to_upstream(aiohttp_server):
    """Proxy should forward request to upstream, preserving headers and body."""

    # Mock upstream server
    async def upstream_handler(request):
        return web.json_response(
            {
                "id": "msg_123",
                "content": [{"type": "text", "text": "Hello"}],
            }
        )

    app_upstream = web.Application()
    app_upstream.router.add_post("/messages", upstream_handler)
    server_upstream = await aiohttp_server(app_upstream)

    # Proxy that forwards to mock upstream
    proxy = DetentProxy(
        port=9996,
        upstream_url=f"http://{server_upstream.host}:{server_upstream.port}",
    )
    await proxy.start()

    try:
        # Make request through proxy
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                f"http://127.0.0.1:{proxy.port}/messages",
                json={"model": "claude-3-opus", "messages": []},
            ) as resp,
        ):
            data = await resp.json()
            assert data["id"] == "msg_123"
    finally:
        await proxy.stop()


def test_extract_tool_calls_from_anthropic_response():
    """Extract tool use blocks from Anthropic API response."""
    proxy = DetentProxy()

    response = {
        "id": "msg_123",
        "content": [
            {"type": "text", "text": "I'll write a file."},
            {
                "type": "tool_use",
                "id": "toolu_01ABC",
                "name": "Write",
                "input": {"file_path": "/src/main.py", "content": "print('hello')"},
            },
        ],
    }

    tool_calls = proxy.extract_tool_calls(response)
    assert len(tool_calls) == 1
    assert tool_calls[0]["name"] == "Write"
    assert tool_calls[0]["input"]["file_path"] == "/src/main.py"


def test_extract_no_tool_calls():
    """Response with no tool use should return empty list."""
    proxy = DetentProxy()

    response = {
        "id": "msg_123",
        "content": [{"type": "text", "text": "Just text response."}],
    }

    tool_calls = proxy.extract_tool_calls(response)
    assert tool_calls == []


@pytest.mark.asyncio
async def test_proxy_creates_session_state_file(tmp_path):
    """Proxy should create and persist session state."""
    session_dir = tmp_path / "session"
    session_dir.mkdir()

    proxy = DetentProxy(port=9995, session_dir=session_dir)
    proxy._session_id = "sess_test_123"
    await proxy._save_session_state()

    session_file = session_dir / "default.json"
    assert session_file.exists()

    data = json.loads(session_file.read_text())
    assert data["session_id"] == "sess_test_123"
    assert "started_at" in data
