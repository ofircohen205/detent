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

"""Shared utilities: detect_agent(), create_session_dir(), _policy_allows(), console, logger."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from rich.console import Console

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult

logger: structlog.stdlib.BoundLogger = structlog.get_logger()
console = Console()


def detect_agent() -> str:
    """Auto-detect the agent type.

    Detection priority:
    1. ANTHROPIC_BASE_URL env var → claude-code
    2. OPENAI_BASE_URL env var → cursor
    3. .claude/settings.json OR .claude/config.json (project or home) → claude-code
    4. .cursor/ in project root or ~/.cursor/ in home dir → cursor
    5. langgraph in pyproject.toml → langgraph
    6. agent.py or agents/ directory → langgraph
    7. Default → unknown
    """
    if os.getenv("ANTHROPIC_BASE_URL"):
        return "claude-code"
    if os.getenv("OPENAI_BASE_URL"):
        return "cursor"

    home = Path.home()
    if (
        (Path(".claude") / "settings.json").exists()
        or (Path(".claude") / "config.json").exists()
        or (home / ".claude" / "settings.json").exists()
        or (home / ".claude" / "config.json").exists()
    ):
        return "claude-code"

    if Path(".cursor").exists() or (home / ".cursor").exists():
        return "cursor"

    pyproject = Path("pyproject.toml")
    if pyproject.exists() and "langgraph" in pyproject.read_text():
        return "langgraph"

    if Path("agent.py").exists() or Path("agents/").exists():
        return "langgraph"

    return "unknown"


def create_session_dir(session_dir: Path | None = None) -> None:
    """Create .detent/session directory."""
    if session_dir is None:
        session_dir = Path(".detent/session")
    session_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Created session directory: {session_dir}")


def _policy_allows(result: VerificationResult, policy: str) -> bool:
    """Determine if policy allows verification result.

    Args:
        result: VerificationResult from pipeline
        policy: Policy profile (strict, standard, permissive)

    Returns:
        True if policy allows, False otherwise
    """
    if policy == "strict":
        return result.passed

    if policy == "standard":
        # Allow warnings, block errors
        return not any(f.severity == "error" for f in result.findings)

    if policy == "permissive":
        # Allow all
        return True

    return result.passed
