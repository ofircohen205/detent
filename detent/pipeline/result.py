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

"""Result models for the verification pipeline.

Finding and VerificationResult are the outputs every VerificationStage produces.
They are pydantic models so they can be serialised to JSON for feedback synthesis.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Finding(BaseModel):
    """A single issue found by a verification stage."""

    severity: Literal["error", "warning", "info"]
    file: str
    line: int | None = None
    column: int | None = None
    message: str
    code: str | None = None
    stage: str
    fix_suggestion: str | None = None


class VerificationResult(BaseModel):
    """The result produced by a single VerificationStage.run() call."""

    stage: str
    passed: bool
    findings: list[Finding]
    duration_ms: float
    metadata: dict[str, Any] = Field(default_factory=dict)

    @property
    def errors(self) -> list[Finding]:
        """All findings with severity == 'error'."""
        return [f for f in self.findings if f.severity == "error"]

    @property
    def has_errors(self) -> bool:
        """True if any finding has severity == 'error'."""
        return any(f.severity == "error" for f in self.findings)
