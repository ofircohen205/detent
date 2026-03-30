"""Pipeline overhead benchmarks.

Documented threshold: proxy overhead < 5 ms per tool call (CLAUDE.md).
These benchmarks measure VerificationPipeline.run() framework cost with
no-op stages, establishing a baseline independent of real stage latency.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from benchmarks.conftest import _make_pipeline

if TYPE_CHECKING:
    from detent.schema import AgentAction

_OVERHEAD_THRESHOLD_MS = 5.0  # documented in CLAUDE.md


def bench_pipeline_no_stages(benchmark: object, py_action: AgentAction) -> None:
    """Pure framework cost with zero stages."""
    pipeline = _make_pipeline(0)

    def run() -> None:
        asyncio.run(pipeline.run(py_action))

    benchmark(run)  # type: ignore[operator]


def bench_pipeline_one_stage_sequential(benchmark: object, py_action: AgentAction) -> None:
    """Framework + one no-op stage, sequential mode."""
    pipeline = _make_pipeline(1)

    def run() -> None:
        asyncio.run(pipeline.run(py_action))

    benchmark(run)  # type: ignore[operator]


def bench_pipeline_five_stages_parallel(benchmark: object, py_action: AgentAction) -> None:
    """Framework + five no-op stages, parallel mode (asyncio.gather)."""
    pipeline = _make_pipeline(5, parallel=True)

    def run() -> None:
        asyncio.run(pipeline.run(py_action))

    benchmark(run)  # type: ignore[operator]


def bench_pipeline_no_stages_threshold(benchmark: object, py_action: AgentAction) -> None:
    """Assert pipeline overhead stays under 5 ms (documented constraint)."""
    pipeline = _make_pipeline(0)

    def run() -> None:
        asyncio.run(pipeline.run(py_action))

    benchmark(run)  # type: ignore[operator]
    stats = benchmark.stats  # type: ignore[union-attr]
    if stats is not None:
        mean_ms = stats["mean"] * 1000
        assert (
            mean_ms < _OVERHEAD_THRESHOLD_MS
        ), f"Pipeline overhead {mean_ms:.2f} ms exceeds {_OVERHEAD_THRESHOLD_MS} ms threshold"


# pytest-benchmark requires test_ prefix to collect benchmark functions
test_pipeline_no_stages = bench_pipeline_no_stages
test_pipeline_one_stage_sequential = bench_pipeline_one_stage_sequential
test_pipeline_five_stages_parallel = bench_pipeline_five_stages_parallel
test_pipeline_no_stages_threshold = bench_pipeline_no_stages_threshold
