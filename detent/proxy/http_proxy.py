"""HTTP reverse proxy for conversation-layer interception (Point 1)."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import aiohttp
from aiohttp import web

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
        self._retry_count = 0
        self._max_retries = 3
        self._session_lock = asyncio.Lock()

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
        return web.json_response(
            {
                "status": "ok",
                "session_id": self._session_id or "none",
            }
        )

    async def _save_session_state(self) -> None:
        """Persist session state to file."""
        if not self._session_id:
            return

        self.session_dir.mkdir(parents=True, exist_ok=True)
        session_file = self.session_dir / "default.json"

        state = {
            "session_id": self._session_id,
            "started_at": datetime.now(UTC).isoformat(),
        }

        session_file.write_text(json.dumps(state, indent=2))
        logger.debug("[proxy] session state saved to %s", session_file)

    async def _forward_with_retry(
        self,
        method: str,
        url: str,
        headers: dict,
        body: bytes | None,
    ) -> tuple[int, dict, bytes]:
        """Forward request with exponential backoff retry on connection failure.

        Args:
            method, url, headers, body: Request details

        Returns:
            (status_code, response_headers, response_body)

        Raises:
            Exception if all retries exhausted
        """
        backoffs = [0.1, 0.2, 0.4]  # 100ms, 200ms, 400ms

        for attempt in range(self._max_retries):
            try:
                async with (
                    aiohttp.ClientSession() as session,
                    session.request(
                        method,
                        url,
                        data=body,
                        headers=headers,
                        timeout=aiohttp.ClientTimeout(total=self.timeout_s),
                    ) as resp,
                ):
                    response_body = await resp.read()
                    return resp.status, dict(resp.headers), response_body
            except (TimeoutError, aiohttp.ClientError) as e:
                if attempt < self._max_retries - 1:
                    wait = backoffs[attempt]
                    logger.warning(
                        "[proxy] request failed (attempt %d/%d), retrying in %.1fs: %s",
                        attempt + 1,
                        self._max_retries,
                        wait,
                        e,
                    )
                    await asyncio.sleep(wait)
                else:
                    logger.error("[proxy] request failed after %d attempts: %s", self._max_retries, e)
                    raise

    async def _proxy_handler(self, request: web.Request) -> web.Response:
        """Forward request to upstream with retry logic."""
        method = request.method
        path = request.match_info.get("path_info", "")

        upstream_url = f"{self.upstream_url}/{path}"
        if request.query_string:
            upstream_url += f"?{request.query_string}"

        body = await request.read() if method in ("POST", "PUT", "PATCH") else None
        headers = {
            k: v
            for k, v in request.headers.items()
            if k.lower() not in ("host", "connection", "transfer-encoding", "upgrade")
        }

        try:
            status, resp_headers, resp_body = await self._forward_with_retry(method, upstream_url, headers, body)
            return web.Response(body=resp_body, status=status, headers=resp_headers)
        except Exception as e:
            logger.error("[proxy] forwarding failed: %s", e)
            return web.json_response({"error": str(e)}, status=502)

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
