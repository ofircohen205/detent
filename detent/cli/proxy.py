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

import click
import structlog

from detent.checkpoint.engine import CheckpointEngine
from detent.config import UPSTREAM_HOST_ANTHROPIC, DetentConfig
from detent.ipc.channel import IPCControlChannel
from detent.pipeline.pipeline import VerificationPipeline
from detent.proxy.http_proxy import DetentProxy
from detent.proxy.session import SessionManager

if TYPE_CHECKING:
    from detent.adapters.http.base import HTTPProxyAdapter

from .app import main

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


def _build_http_adapter(config: DetentConfig, session_manager: SessionManager) -> HTTPProxyAdapter | None:
    from detent.adapters import ADAPTERS
    from detent.adapters.http.base import HTTPProxyAdapter

    adapter_cls = ADAPTERS.get(config.agent)
    if adapter_cls is None or not issubclass(adapter_cls, HTTPProxyAdapter):
        logger.warning("[proxy] no HTTP adapter for agent %r", config.agent)
        return None
    return adapter_cls(session_manager=session_manager)


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

    http_adapter = _build_http_adapter(config, session_manager)
    upstream_host = http_adapter.upstream_host if http_adapter is not None else UPSTREAM_HOST_ANTHROPIC

    proxy = DetentProxy(
        port=config.proxy.port,
        upstream_url=f"https://{upstream_host}",
        strict_mode=config.strict_mode,
        session_manager=session_manager,
        http_adapter=http_adapter,
    )
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
