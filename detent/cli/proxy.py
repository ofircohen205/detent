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

"""Command to launch the Detent HTTP reverse proxy."""

from __future__ import annotations

import asyncio
import signal
import uuid
from contextlib import suppress
from typing import TYPE_CHECKING
from urllib.parse import urlparse

import click
import structlog

from detent.checkpoint.engine import CheckpointEngine
from detent.config import UPSTREAM_HOST_ANTHROPIC, UPSTREAM_HOST_OPENAI, DetentConfig
from detent.ipc.channel import IPCControlChannel
from detent.pipeline.pipeline import VerificationPipeline
from detent.proxy.http_proxy import DetentProxy
from detent.proxy.session import SessionManager

if TYPE_CHECKING:
    from detent.adapters.hook.base import HookAdapter
    from detent.adapters.http.base import HTTPProxyAdapter

from .app import main

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_DEFAULT_UPSTREAM_HOSTS: dict[str, str] = {
    "claude-code": UPSTREAM_HOST_ANTHROPIC,
    "codex": UPSTREAM_HOST_OPENAI,
}


def _resolve_proxy_upstream(config: DetentConfig) -> str:
    if config.proxy.upstream_url:
        return config.proxy.upstream_url

    upstream_host = _DEFAULT_UPSTREAM_HOSTS.get(config.agent, UPSTREAM_HOST_ANTHROPIC)
    if config.agent not in _DEFAULT_UPSTREAM_HOSTS:
        logger.warning("[proxy] no default upstream for agent %r; falling back to Anthropic", config.agent)
    return f"https://{upstream_host}"


def _register_hook_adapters(proxy: DetentProxy, config: DetentConfig, session_manager: SessionManager) -> None:
    """Register Point 2 hook adapters on the proxy app before it starts."""
    hook_adapter: HookAdapter | None = None
    if config.agent == "claude-code":
        from detent.adapters.hook.claude_code import ClaudeCodeHookAdapter

        hook_adapter = ClaudeCodeHookAdapter(session_manager=session_manager)
    elif config.agent == "codex":
        from detent.adapters.hook.codex import CodexHookAdapter

        hook_adapter = CodexHookAdapter(session_manager=session_manager)

    if hook_adapter is not None:
        hook_adapter.register(proxy.app)
        logger.info("[proxy] registered %s hook adapter at %s", config.agent, hook_adapter.route)


def _build_http_adapter(
    config: DetentConfig, session_manager: SessionManager, upstream_url: str
) -> HTTPProxyAdapter | None:
    from detent.adapters.http.providers import AnthropicResponseAdapter, OpenAIResponseAdapter

    upstream_host = urlparse(upstream_url).hostname or ""
    observed_agent = config.agent
    if upstream_host == UPSTREAM_HOST_ANTHROPIC:
        return AnthropicResponseAdapter(session_manager=session_manager, observed_agent=observed_agent)
    if upstream_host == UPSTREAM_HOST_OPENAI:
        return OpenAIResponseAdapter(session_manager=session_manager, observed_agent=observed_agent)

    logger.warning("[proxy] no response adapter for upstream host %r", upstream_host)
    return None


async def _run_proxy() -> None:
    config = DetentConfig.load()
    pipeline = VerificationPipeline.from_config(config)
    checkpoint_engine = CheckpointEngine()
    ipc_channel = IPCControlChannel(timeout_ms=config.ipc_timeout_ms)
    await ipc_channel.start_server()

    session_manager = SessionManager(
        checkpoint_engine=checkpoint_engine,
        pipeline=pipeline,
        ipc_channel=ipc_channel,
    )
    session_id = f"proxy_{uuid.uuid4().hex[:8]}"
    await session_manager.start_session(session_id=session_id)

    upstream_url = _resolve_proxy_upstream(config)
    http_adapter = _build_http_adapter(config, session_manager, upstream_url)

    proxy = DetentProxy(
        port=config.proxy.port,
        upstream_url=upstream_url,
        strict_mode=config.strict_mode,
        session_manager=session_manager,
        http_adapter=http_adapter,
    )
    _register_hook_adapters(proxy, config, session_manager)
    await proxy.start()

    loop = asyncio.get_running_loop()
    stop_event = loop.create_future()

    def _signal_handler() -> None:
        if not stop_event.done():
            stop_event.set_result(None)

    for sig in (signal.SIGINT, signal.SIGTERM):
        with suppress(NotImplementedError, AttributeError):
            loop.add_signal_handler(sig, _signal_handler)

    logger.info("proxy running; press Ctrl+C to stop")
    try:
        await stop_event
    finally:
        await proxy.stop()
        await session_manager.end_session()
        await ipc_channel.stop_server()


@main.command()
def proxy() -> None:
    """Start the Detent HTTP reverse proxy."""
    try:
        asyncio.run(_run_proxy())
    except Exception as exc:  # pragma: no cover
        raise click.ClickException(f"proxy command failed: {exc}") from exc
