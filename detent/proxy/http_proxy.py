# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Detent Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""HTTP reverse proxy for conversation-layer interception (Point 1)."""

from __future__ import annotations

import asyncio
import logging
import ssl
import time
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import aiohttp
import certifi
from aiohttp import web

from detent.circuit_breaker import CircuitBreaker, CircuitOpenError
from detent.config import ALLOWED_UPSTREAM_HOSTS
from detent.observability.metrics import record_proxy_request, record_proxy_retry
from detent.observability.tracer import get_tracer
from detent.proxy.types import SessionState

logger = logging.getLogger(__name__)


class DetentProxy:
    """HTTP reverse proxy intercepting LLM API traffic.

    Listens on 127.0.0.1:{port}, forwards all requests to upstream LLM API.
    """

    def __init__(
        self,
        port: int = 7070,
        upstream_url: str = "https://api.anthropic.com",
        connect_timeout_s: float = 10.0,
        session_dir: Path | str | None = None,
        ssl_context: ssl.SSLContext | None = None,
        strict_mode: bool = False,
    ) -> None:
        """Initialize HTTP proxy.

        Args:
            port: Port to listen on (default 7070)
            upstream_url: Upstream LLM API base URL
            connect_timeout_s: TCP connect timeout in seconds (default 10). No total
                timeout is applied — LLM API calls can stream for minutes.
            session_dir: Directory for session state files (default .detent/session)
            ssl_context: Custom SSL context for upstream connections. Defaults to
                a context using the certifi CA bundle, which avoids macOS keychain issues.
        """
        self.port = port
        _host = urlparse(upstream_url).hostname or ""
        if _host not in ALLOWED_UPSTREAM_HOSTS:
            raise ValueError(f"upstream_url host {_host!r} is not in allowlist: {sorted(ALLOWED_UPSTREAM_HOSTS)}")
        self.upstream_url = upstream_url
        self.connect_timeout_s = connect_timeout_s
        self.session_dir = Path(session_dir or ".detent/session")
        self.is_running = False
        self._app: web.Application = web.Application()
        self._runner: web.AppRunner | None = None
        self._session_id: str | None = None
        self._retry_count = 0
        self._max_retries = 3
        self._session_lock = asyncio.Lock()
        self._routes_configured = False
        self.strict_mode = strict_mode
        self._proxy_breaker = CircuitBreaker(name="proxy")
        if ssl_context is not None:
            self._ssl_context = ssl_context
        else:
            self._ssl_context = ssl.create_default_context(cafile=certifi.where())

    async def start(self) -> None:
        """Start the HTTP proxy server."""
        if not self._routes_configured:
            self._app.router.add_get("/health", self._health_handler)
            self._app.router.add_route("*", "/{path_info:.*}", self._proxy_handler)
            self._routes_configured = True

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
        return web.json_response({"status": "ok"})

    async def _save_session_state(self) -> None:
        """Persist session state to file."""
        if not self._session_id:
            return

        self.session_dir.mkdir(parents=True, exist_ok=True)
        session_file = self.session_dir / "default.json"

        state = SessionState(
            session_id=self._session_id,
            started_at=datetime.now(UTC).isoformat(),
        )

        session_file.write_text(state.model_dump_json(indent=2))
        logger.debug("[proxy] session state saved to %s", session_file)

    async def _forward_with_retry(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        body: bytes | None,
    ) -> tuple[int, dict[str, str], bytes]:
        """Forward request with exponential backoff retry on connection failure.

        Args:
            method, url, headers, body: Request details

        Returns:
            (status_code, response_headers, response_body)

        Raises:
            Exception if all retries exhausted
        """
        backoffs = [0.1, 0.2, 0.4]  # 100ms, 200ms, 400ms
        tracer = get_tracer(__name__)
        upstream_host = urlparse(url).hostname or "<unknown>"

        for attempt in range(self._max_retries):
            attempt_number = attempt + 1
            span_attrs = {
                "detent.proxy.upstream_host": upstream_host,
                "detent.proxy.method": method,
                "detent.retry.attempt": attempt_number,
            }
            with tracer.start_as_current_span("detent.proxy.request", attributes=span_attrs) as span:
                try:
                    connector = aiohttp.TCPConnector(ssl=self._ssl_context)
                    start = time.perf_counter()
                    async with (
                        aiohttp.ClientSession(connector=connector) as session,
                        session.request(
                            method,
                            url,
                            data=body,
                            headers=headers,
                            timeout=aiohttp.ClientTimeout(
                                connect=self.connect_timeout_s,
                                total=None,
                            ),
                        ) as resp,
                    ):
                        response_body = await resp.read()
                        duration_ms = (time.perf_counter() - start) * 1000
                        span.set_attribute("detent.proxy.status_code", resp.status)
                        record_proxy_request(upstream_host, resp.status, duration_ms)
                        return resp.status, dict(resp.headers), response_body
                except (TimeoutError, aiohttp.ClientError) as e:
                    record_proxy_retry(upstream_host, attempt_number)
                    if attempt < self._max_retries - 1:
                        wait = backoffs[attempt]
                        logger.warning(
                            "[proxy] request failed (attempt %d/%d), retrying in %.1fs: %s",
                            attempt_number,
                            self._max_retries,
                            wait,
                            e,
                        )
                        await asyncio.sleep(wait)
                    else:
                        logger.error(
                            "[proxy] request failed after %d attempts: %s",
                            self._max_retries,
                            e,
                        )
                        raise

        msg = "All retries exhausted"
        raise RuntimeError(msg)

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
            coro = self._forward_with_retry(method, upstream_url, headers, body)
            status, resp_headers, resp_body = await self._proxy_breaker.call(coro)
            return web.Response(body=resp_body, status=status, headers=resp_headers)
        except CircuitOpenError:
            if self.strict_mode:
                return web.json_response({"error": "proxy circuit breaker open"}, status=503)
            status, resp_headers, resp_body = await self._forward_with_retry(method, upstream_url, headers, body)
            return web.Response(body=resp_body, status=status, headers=resp_headers)
        except Exception as e:
            logger.error("[proxy] forwarding failed: %s", e)
            return web.json_response({"error": "Upstream connection failed"}, status=502)

    @property
    def app(self) -> web.Application:
        """Expose aiohttp app for hook adapter registration."""
        return self._app
