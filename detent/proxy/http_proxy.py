"""HTTP reverse proxy for conversation-layer interception (Point 1)."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

from detent.proxy.types import DetentSessionConflictError, SessionState

logger = logging.getLogger(__name__)


class DetentProxy:
    """HTTP reverse proxy intercepting LLM API traffic.

    Listens on 127.0.0.1:{port}, forwards all requests to upstream LLM API,
    extracts tool calls before returning response to client.
    """

    def __init__(
        self,
        port: int = 7070,
        upstream_url: str = "https://api.anthropic.com",
        timeout_s: int = 5,
        session_dir: Path | str | None = None,
    ) -> None:
        """Initialize HTTP proxy.

        Args:
            port: Port to listen on (default 7070)
            upstream_url: Upstream LLM API base URL
            timeout_s: Request timeout in seconds
            session_dir: Directory for session state files (default .detent/session)
        """
        self.port = port
        self.upstream_url = upstream_url
        self.timeout_s = timeout_s
        self.session_dir = Path(session_dir or ".detent/session")
        self.is_running = False
        self._app: web.Application | None = None
        self._runner: web.AppRunner | None = None
        self._session_id: str | None = None

    async def start(self) -> None:
        """Start the HTTP proxy server."""
        self._app = web.Application()
        self._app.router.add_get("/health", self._health_handler)
        self._app.router.add_route("*", "/{path_info:.*}", self._proxy_handler)

        self._runner = web.AppRunner(self._app)
        await self._runner.setup()

        site = web.TCPSite(self._runner, "127.0.0.1", self.port)
        await site.start()

        self.is_running = True
        logger.info("[proxy] started on http://127.0.0.1:%d", self.port)

    async def stop(self) -> None:
        """Stop the HTTP proxy server."""
        if self._runner:
            await self._runner.cleanup()
        self.is_running = False
        logger.info("[proxy] stopped")

    async def _health_handler(self, request: web.Request) -> web.Response:
        """Handle GET /health."""
        return web.json_response({
            "status": "ok",
            "session_id": self._session_id or "none",
        })

    async def _proxy_handler(self, request: web.Request) -> web.Response:
        """Forward request to upstream, preserving method, headers, body."""
        method = request.method
        path = request.match_info.get("path_info", "")

        # Reconstruct upstream URL
        upstream_url = f"{self.upstream_url}/{path}"
        if request.query_string:
            upstream_url += f"?{request.query_string}"

        # Forward body if present
        body = await request.read() if method in ("POST", "PUT", "PATCH") else None

        # Forward headers (skip hop-by-hop headers)
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in ("host", "connection", "transfer-encoding", "upgrade")
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.request(
                    method,
                    upstream_url,
                    data=body,
                    headers=headers,
                    timeout=aiohttp.ClientTimeout(total=self.timeout_s),
                ) as upstream_resp:
                    response_body = await upstream_resp.read()

                    # Return upstream response with same status and headers
                    return web.Response(
                        body=response_body,
                        status=upstream_resp.status,
                        headers=dict(upstream_resp.headers),
                    )
        except asyncio.TimeoutError:
            logger.error("[proxy] upstream request timeout for %s %s", method, upstream_url)
            return web.json_response(
                {"error": "Upstream timeout"},
                status=504,
            )
        except Exception as e:
            logger.error("[proxy] forwarding failed: %s", e)
            return web.json_response(
                {"error": str(e)},
                status=502,
            )

    def extract_tool_calls(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract tool use blocks from Anthropic API response.

        Args:
            response: Anthropic API response dict

        Returns:
            List of tool use blocks (empty if none)
        """
        tool_calls = []
        content = response.get("content", [])

        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tool_calls.append(block)

        return tool_calls
