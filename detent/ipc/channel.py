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

"""IPC control channel for proxy ↔ adapter communication."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from detent.proxy.types import IPCMessage

logger = logging.getLogger(__name__)


class IPCControlChannel:
    """Unix domain socket server for IPC communication.

    Uses NDJSON (Newline Delimited JSON) protocol:
    Each message is a JSON object followed by newline.
    """

    def __init__(
        self,
        socket_path: Path | str = ".detent/run/control.sock",
        timeout_ms: int = 4000,
    ) -> None:
        """Initialize IPC control channel.

        Args:
            socket_path: Path to Unix domain socket
            timeout_ms: Message receive timeout in milliseconds
        """
        self.socket_path = Path(socket_path)
        self.timeout_ms = timeout_ms
        self.is_running = False
        self._server: asyncio.Server | None = None
        self._clients: set[asyncio.StreamWriter] = set()
        self._lock = asyncio.Lock()

    async def start_server(self) -> None:
        """Start the IPC control channel server."""
        # Create socket directory if needed
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)

        # Remove stale socket file
        if self.socket_path.exists():
            self.socket_path.unlink()

        self._server = await asyncio.start_unix_server(
            self._handle_connection,
            path=str(self.socket_path),
        )

        self.is_running = True
        logger.info("[ipc] server started at %s", self.socket_path)

    async def stop_server(self) -> None:
        """Stop the IPC control channel server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()

        # Close all client connections
        async with self._lock:
            for writer in self._clients:
                writer.close()
                with contextlib.suppress(Exception):
                    await writer.wait_closed()
            self._clients.clear()

        self.is_running = False
        logger.info("[ipc] server stopped")

    async def _handle_connection(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Handle incoming client connection."""
        async with self._lock:
            self._clients.add(writer)

        logger.debug("[ipc] client connected")

        try:
            while self.is_running:
                try:
                    line = await asyncio.wait_for(
                        reader.readuntil(b"\n"),
                        timeout=self.timeout_ms / 1000.0,
                    )

                    if not line:
                        break

                    await self._process_message(line)
                except TimeoutError:
                    logger.debug("[ipc] receive timeout")
                    break
        except Exception as e:
            logger.error("[ipc] connection error: %s", e)
        finally:
            async with self._lock:
                self._clients.discard(writer)
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
            logger.debug("[ipc] client disconnected")

    async def _process_message(self, line: bytes) -> None:
        """Process received NDJSON message."""
        try:
            data = json.loads(line.decode("utf-8"))
            logger.debug("[ipc] received message: type=%s", data.get("type"))
        except json.JSONDecodeError as e:
            logger.error("[ipc] malformed message: %s", e)

    def serialize_message(self, msg: IPCMessage) -> bytes:
        """Serialize message to NDJSON format."""
        data = json.dumps(msg.model_dump()).encode("utf-8") + b"\n"
        return data

    async def send_message(self, msg: IPCMessage) -> None:
        """Broadcast message to all connected clients."""
        data = self.serialize_message(msg)

        async with self._lock:
            for writer in self._clients:
                try:
                    writer.write(data)
                    await writer.drain()
                except Exception as e:
                    logger.error("[ipc] failed to send message: %s", e)
