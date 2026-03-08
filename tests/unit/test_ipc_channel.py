"""Tests for IPC control channel."""

import asyncio
import contextlib
import json
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest

from detent.ipc.channel import IPCControlChannel
from detent.proxy.types import IPCMessage, IPCMessageType


@pytest.fixture
def short_socket_path() -> Generator[Path, None, None]:
    """Provide a short socket path to avoid AF_UNIX path length limits."""
    import shutil

    # Use a shorter temp directory to stay under 108 byte limit
    tmpdir = tempfile.mkdtemp(prefix="ipc_")
    yield Path(tmpdir) / "sock"
    # Cleanup
    if Path(tmpdir).exists():
        shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.mark.asyncio
async def test_ipc_channel_starts_and_stops(short_socket_path: Path) -> None:
    """IPC channel should start socket server and stop cleanly."""
    socket_path = short_socket_path

    channel = IPCControlChannel(socket_path=socket_path)
    await channel.start_server()

    assert channel.is_running is True
    assert socket_path.exists()

    await channel.stop_server()
    assert channel.is_running is False


@pytest.mark.asyncio
async def test_ipc_send_and_receive_message(short_socket_path: Path) -> None:
    """Send and receive NDJSON message through IPC."""
    socket_path = short_socket_path

    channel = IPCControlChannel(socket_path=socket_path, timeout_ms=1000)
    await channel.start_server()

    # In real usage, this would be called from adapter
    # For testing, we'll verify message serialization
    msg = IPCMessage(
        type=IPCMessageType.SESSION_START,
        data={"session_id": "sess_123", "checkpoint_ref": "chk_001"},
        timestamp="2026-03-07T10:00:00Z",
    )

    serialized = channel.serialize_message(msg)
    assert serialized.endswith(b"\n")
    assert b"session_start" in serialized

    await channel.stop_server()


@pytest.mark.asyncio
async def test_ipc_channel_accepts_connections(short_socket_path: Path) -> None:
    """IPC channel should accept client connections."""
    socket_path = short_socket_path

    channel = IPCControlChannel(socket_path=socket_path, timeout_ms=2000)
    await channel.start_server()

    # Open a client connection
    reader, writer = await asyncio.open_unix_connection(str(socket_path))

    # Send a message
    msg = IPCMessage(
        type=IPCMessageType.TOOL_INTERCEPTED,
        data={"tool_name": "Write", "file_path": "test.py"},
        timestamp="2026-03-07T10:00:00Z",
    )
    serialized = channel.serialize_message(msg)
    writer.write(serialized)
    await writer.drain()

    # Close connection
    writer.close()
    await writer.wait_closed()

    await channel.stop_server()


@pytest.mark.asyncio
async def test_ipc_broadcast_to_multiple_clients(short_socket_path: Path) -> None:
    """IPC should broadcast messages to all connected clients."""
    socket_path = short_socket_path

    channel = IPCControlChannel(socket_path=socket_path, timeout_ms=2000)
    await channel.start_server()

    # Connect two clients
    reader1, writer1 = await asyncio.open_unix_connection(str(socket_path))
    reader2, writer2 = await asyncio.open_unix_connection(str(socket_path))

    # Give server time to register connections
    await asyncio.sleep(0.05)

    # Broadcast a message
    msg = IPCMessage(
        type=IPCMessageType.VERIFICATION_RESULT,
        data={"status": "passed"},
        timestamp="2026-03-07T10:00:00Z",
    )
    await channel.send_message(msg)

    # Give the server time to send
    await asyncio.sleep(0.05)

    # Try to receive on both clients (should be immediate)
    try:
        line1 = await asyncio.wait_for(reader1.readuntil(b"\n"), timeout=0.5)
        line2 = await asyncio.wait_for(reader2.readuntil(b"\n"), timeout=0.5)

        # Both should receive the message
        data1 = json.loads(line1.decode("utf-8"))
        data2 = json.loads(line2.decode("utf-8"))

        assert data1["type"] == "verification_result"
        assert data2["type"] == "verification_result"
    finally:
        # Cleanup
        writer1.close()
        writer2.close()
        with contextlib.suppress(Exception):
            await writer1.wait_closed()
        with contextlib.suppress(Exception):
            await writer2.wait_closed()

    await channel.stop_server()


@pytest.mark.asyncio
async def test_ipc_malformed_message_handling(short_socket_path: Path) -> None:
    """IPC should handle malformed messages gracefully."""
    socket_path = short_socket_path

    channel = IPCControlChannel(socket_path=socket_path, timeout_ms=2000)
    await channel.start_server()

    # Connect a client
    reader, writer = await asyncio.open_unix_connection(str(socket_path))

    # Send malformed JSON
    writer.write(b"not valid json\n")
    await writer.drain()

    # Server should still be running and accept another connection
    await asyncio.sleep(0.1)

    assert channel.is_running is True

    # Close connection
    writer.close()
    await writer.wait_closed()

    await channel.stop_server()
