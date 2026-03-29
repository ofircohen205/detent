"""Checkpoint latency benchmarks.

Documented thresholds (CLAUDE.md):
  - Rollback latency: < 500 ms
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from detent.checkpoint.engine import CheckpointEngine

_ROLLBACK_THRESHOLD_MS = 500.0  # documented in CLAUDE.md


def bench_savepoint_1kb(benchmark: object, checkpoint_engine: CheckpointEngine, tmp_1kb: Path) -> None:
    """Savepoint a 1 KB Python file."""
    i = 0

    def run() -> None:
        nonlocal i
        asyncio.run(checkpoint_engine.savepoint(f"chk_1kb_{i}", [str(tmp_1kb)]))  # type: ignore[union-attr]
        i += 1

    benchmark(run)  # type: ignore[operator]


def bench_savepoint_100kb(benchmark: object, checkpoint_engine: CheckpointEngine, tmp_100kb: Path) -> None:
    """Savepoint a 100 KB Python file."""
    i = 0

    def run() -> None:
        nonlocal i
        asyncio.run(checkpoint_engine.savepoint(f"chk_100kb_{i}", [str(tmp_100kb)]))  # type: ignore[union-attr]
        i += 1

    benchmark(run)  # type: ignore[operator]


def bench_rollback_1kb(benchmark: object, checkpoint_engine: CheckpointEngine, tmp_1kb: Path) -> None:
    """Rollback a 1 KB file. Asserts < 500 ms threshold."""
    original = tmp_1kb.read_bytes()
    asyncio.run(checkpoint_engine.savepoint("chk_roll_1kb", [str(tmp_1kb)]))  # type: ignore[union-attr]

    def run() -> None:
        tmp_1kb.write_bytes(b"y" * len(original))
        asyncio.run(checkpoint_engine.rollback("chk_roll_1kb"))  # type: ignore[union-attr]

    benchmark(run)  # type: ignore[operator]
    if benchmark.stats is not None:  # type: ignore[union-attr]
        mean_ms = benchmark.stats["mean"] * 1000  # type: ignore[union-attr]
        assert (
            mean_ms < _ROLLBACK_THRESHOLD_MS
        ), f"Rollback latency {mean_ms:.2f} ms exceeds {_ROLLBACK_THRESHOLD_MS} ms threshold"
    assert tmp_1kb.read_bytes() == original


def bench_rollback_100kb(benchmark: object, checkpoint_engine: CheckpointEngine, tmp_100kb: Path) -> None:
    """Rollback a 100 KB file."""
    original = tmp_100kb.read_bytes()
    asyncio.run(checkpoint_engine.savepoint("chk_roll_100kb", [str(tmp_100kb)]))  # type: ignore[union-attr]

    def run() -> None:
        tmp_100kb.write_bytes(b"y" * len(original))
        asyncio.run(checkpoint_engine.rollback("chk_roll_100kb"))  # type: ignore[union-attr]

    benchmark(run)  # type: ignore[operator]
    assert tmp_100kb.read_bytes() == original


# pytest collection aliases
test_savepoint_1kb = bench_savepoint_1kb
test_savepoint_100kb = bench_savepoint_100kb
test_rollback_1kb = bench_rollback_1kb
test_rollback_100kb = bench_rollback_100kb
