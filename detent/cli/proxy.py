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
import logging
import signal
from contextlib import suppress

import click

from detent.config import DetentConfig
from detent.proxy.http_proxy import DetentProxy

from .app import main

logger = logging.getLogger(__name__)


async def _run_proxy() -> None:
    config = DetentConfig.load()
    proxy = DetentProxy(port=config.proxy.port)
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
    await stop_event
    await proxy.stop()


@main.command()
def proxy() -> None:
    """Start the Detent HTTP reverse proxy."""
    try:
        asyncio.run(_run_proxy())
    except Exception as exc:  # pragma: no cover
        raise click.ClickException(f"proxy command failed: {exc}") from exc
