"""Tests for HTTP reverse proxy."""

import json
from unittest.mock import MagicMock

import aiohttp
import pytest

from detent.adapters.hook.codex import CodexHookAdapter
from detent.proxy.http_proxy import _HOP_BY_HOP_RESPONSE_HEADERS, DetentProxy


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
    """GET /health should return status ok (no session_id exposed)."""
    proxy = DetentProxy(port=9998, upstream_url="https://api.anthropic.com")
    await proxy.start()

    try:
        async with aiohttp.ClientSession() as session, session.get(f"http://127.0.0.1:{proxy.port}/health") as resp:
            assert resp.status == 200
            data = await resp.json()
            assert data["status"] == "ok"
            assert "session_id" not in data
    finally:
        await proxy.stop()


def test_proxy_rejects_unlisted_upstream_host() -> None:
    """DetentProxy raises ValueError for non-allowlisted upstream URLs."""
    with pytest.raises(ValueError, match="not in allowlist"):
        DetentProxy(upstream_url="https://evil.attacker.com")


def test_proxy_accepts_anthropic_upstream() -> None:
    proxy = DetentProxy(upstream_url="https://api.anthropic.com")
    assert proxy.upstream_url == "https://api.anthropic.com"


def test_proxy_accepts_openai_upstream() -> None:
    proxy = DetentProxy(upstream_url="https://api.openai.com")
    assert proxy.upstream_url == "https://api.openai.com"


@pytest.mark.asyncio
async def test_hook_route_registered_before_proxy_handler():
    """Hook routes should be matched before the catch-all proxy handler (which returns 502)."""
    proxy = DetentProxy(port=9996, upstream_url="https://api.anthropic.com")
    adapter = CodexHookAdapter(session_manager=MagicMock())
    adapter.register(proxy.app)
    await proxy.start()

    try:
        async with (
            aiohttp.ClientSession() as session,
            session.post(
                f"http://127.0.0.1:{proxy.port}/hooks/codex",
                json={},
            ) as resp,
        ):
            # Hook adapter handles the request (not the catch-all proxy → 502)
            assert resp.status != 502
    finally:
        await proxy.stop()


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


def test_hop_by_hop_headers_strips_content_encoding():
    """content-encoding and content-length must be in the hop-by-hop strip set.

    aiohttp auto-decompresses gzip response bodies on resp.read(), so forwarding
    Content-Encoding: gzip causes the downstream client to attempt a second
    decompression, resulting in ZlibError. content-length is also stale after
    decompression since the body size changes.
    """
    assert "content-encoding" in _HOP_BY_HOP_RESPONSE_HEADERS
    assert "content-length" in _HOP_BY_HOP_RESPONSE_HEADERS
