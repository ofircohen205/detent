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

"""Reusable async circuit breaker used by proxy and stages."""

from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING, Any, Literal, TypeVar

import structlog

from detent.observability.metrics import increment_circuit_breaker_trip, update_circuit_breaker_state

if TYPE_CHECKING:
    from collections.abc import Coroutine

T = TypeVar("T")
logger: structlog.stdlib.BoundLogger = structlog.get_logger()


class CircuitOpenError(Exception):
    """Raised when a circuit breaker is open."""

    def __init__(self, name: str) -> None:
        super().__init__(f"Circuit '{name}' is open")
        self.name = name


class CircuitBreaker:
    """Thread/async-safe circuit breaker (CLOSED → OPEN → HALF_OPEN)."""

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_window_s: float = 60.0,
    ) -> None:
        self.name = name
        self._state: Literal["closed", "open", "half_open"] = "closed"
        self._failure_threshold = failure_threshold
        self._recovery_window_s = recovery_window_s
        self._failure_count = 0
        self._opened_at: float | None = None
        self._probing = False
        self._lock = asyncio.Lock()
        update_circuit_breaker_state(self.name, 0)

    @property
    def state(self) -> Literal["closed", "open", "half_open"]:
        return self._state

    async def call(self, coro: Coroutine[Any, Any, T]) -> T:
        """Execute *coro* under circuit-breaker protection.

        Raises:
            CircuitOpenError: If the circuit is open and the recovery
                window has not elapsed yet.
        """
        async with self._lock:
            if self._state == "open":
                now = time.monotonic()
                if self._opened_at is not None and now - self._opened_at < self._recovery_window_s:
                    logger.debug("Circuit '%s' open (waiting for recovery window)", self.name)
                    raise CircuitOpenError(self.name)
                if self._probing:
                    logger.debug("Circuit '%s' already probing", self.name)
                    raise CircuitOpenError(self.name)
                self._state = "half_open"
                self._probing = True
                update_circuit_breaker_state(self.name, 2)
        try:
            result = await coro
        except Exception:
            async with self._lock:
                self._probing = False
                self._on_failure()
            raise
        else:
            async with self._lock:
                self._probing = False
                self._on_success()
            return result

    def _on_failure(self) -> None:
        if self._state == "half_open":
            self._state = "open"
            self._opened_at = time.monotonic()
            increment_circuit_breaker_trip(self.name)
            update_circuit_breaker_state(self.name, 1)
        elif self._state == "closed":
            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._state = "open"
                self._opened_at = time.monotonic()
                increment_circuit_breaker_trip(self.name)
                update_circuit_breaker_state(self.name, 1)

    def _on_success(self) -> None:
        self._state = "closed"
        self._failure_count = 0
        self._opened_at = None
        update_circuit_breaker_state(self.name, 0)
