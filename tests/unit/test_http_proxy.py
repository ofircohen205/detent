"""Tests for HTTP reverse proxy."""

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
        async with aiohttp.ClientSession() as session:
            async with session.get(f"http://127.0.0.1:{proxy.port}/health") as resp:
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
        return web.json_response({
            "id": "msg_123",
            "content": [{"type": "text", "text": "Hello"}],
        })

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
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"http://127.0.0.1:{proxy.port}/messages",
                json={"model": "claude-3-opus", "messages": []},
            ) as resp:
                data = await resp.json()
                assert data["id"] == "msg_123"
    finally:
        await proxy.stop()
