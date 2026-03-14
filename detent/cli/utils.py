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

import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING

from rich.console import Console

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult

logger = logging.getLogger(__name__)
console = Console()


def detect_agent() -> str:
    """Auto-detect the agent type.

    Detection priority:
    1. ANTHROPIC_BASE_URL or OPENAI_BASE_URL env vars
    2. Claude Code config at ~/.claude/config.json
    3. langgraph in pyproject.toml
    4. agent.py or agents/ directory
    5. Default to claude-code
    """
    # Check environment variables
    if os.getenv("ANTHROPIC_BASE_URL"):
        return "claude-code"
    if os.getenv("OPENAI_BASE_URL"):
        return "cursor"

    # Check for Claude Code config
    cc_config = Path.home() / ".claude" / "config.json"
    if cc_config.exists():
        return "claude-code"

    # Check for langgraph in pyproject.toml
    pyproject = Path("pyproject.toml")
    if pyproject.exists():
        content = pyproject.read_text()
        if "langgraph" in content:
            return "langgraph"

    # Check for agent files
    if Path("agent.py").exists() or Path("agents/").exists():
        return "langgraph"

    # Default
    return "claude-code"


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
