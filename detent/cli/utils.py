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

"""Shared utilities: detect_agent(), create_session_dir(), _policy_allows(), and logger."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
import structlog

if TYPE_CHECKING:
    from detent.pipeline.result import VerificationResult

logger: structlog.stdlib.BoundLogger = structlog.get_logger()

_DETENT_HOOK_MATCHER = "Write|Edit|NotebookEdit"


class CLIConsole:
    """Small wrapper matching the subset of Rich Console used by the CLI."""

    def print(self, message: object = "") -> None:
        click.echo(self._strip_markup(str(message)))

    def _strip_markup(self, value: str) -> str:
        replacements = {
            "[cyan]": "",
            "[/cyan]": "",
            "[yellow]": "",
            "[/yellow]": "",
            "[green]": "",
            "[/green]": "",
            "[bold]": "",
            "[/bold]": "",
            "[magenta]": "",
            "[/magenta]": "",
            "[blue]": "",
            "[/blue]": "",
        }
        for old, new in replacements.items():
            value = value.replace(old, new)
        return value


console = CLIConsole()


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


def configure_claude_code_hook(port: int = 7070) -> bool:
    """Write the Detent PreToolUse hook into .claude/settings.json.

    Creates or merges into the project-level Claude Code settings file so
    every tool call is sent to the Detent hook endpoint for enforcement.

    Args:
        port: Port the Detent proxy is listening on (default 7070).

    Returns:
        True if the hook was added or was already present, False on error.
    """
    if not (1 <= port <= 65535):
        raise ValueError(f"port must be 1-65535, got {port!r}")

    settings_path = Path(".claude") / "settings.json"

    # Reject symlinks that escape the project root (mirrors savepoint.py pattern)
    project_root = Path.cwd().resolve()
    try:
        resolved = settings_path.parent.resolve()
    except OSError:
        resolved = settings_path.parent
    if not resolved.is_relative_to(project_root):
        logger.error("Settings path %s escapes project root; refusing to write", resolved)
        return False

    hook_command = (
        f"curl -s -X POST http://127.0.0.1:{port}/hooks/claude-code" f" -H 'Content-Type: application/json' -d @-"
    )
    detent_hook = {"type": "command", "command": hook_command}

    settings: dict[str, Any] = {}
    if settings_path.exists():
        try:
            settings = json.loads(settings_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read %s: %s", settings_path, e)
            return False

    hooks: dict[str, Any] = settings.setdefault("hooks", {})
    pretool_entries: list[dict[str, Any]] = hooks.setdefault("PreToolUse", [])

    # Identify stale and correct Detent entries
    stale = [
        entry
        for entry in pretool_entries
        if any("/hooks/claude-code" in h.get("command", "") for h in entry.get("hooks", []))
        and entry.get("matcher") != _DETENT_HOOK_MATCHER
    ]
    correct = [
        entry
        for entry in pretool_entries
        if any("/hooks/claude-code" in h.get("command", "") for h in entry.get("hooks", []))
        and entry.get("matcher") == _DETENT_HOOK_MATCHER
    ]

    if correct and not stale:
        logger.debug("Detent hook already correct in %s; skipping", settings_path)
        return True

    if stale:
        logger.info("Migrating %d stale Detent hook entry/entries in %s", len(stale), settings_path)
        for entry in stale:
            pretool_entries.remove(entry)

    if not correct:
        pretool_entries.append({"matcher": _DETENT_HOOK_MATCHER, "hooks": [detent_hook]})

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        settings_path.write_text(json.dumps(settings, indent=2) + "\n")
    except OSError as e:
        logger.warning("Could not write %s: %s", settings_path, e)
        return False
    logger.info("Wrote Detent hook to %s", settings_path)
    return True


def configure_codex_hook(port: int = 7070) -> bool:
    """Write the Detent PreToolUse hook into .codex/hooks.json for Codex CLI.

    Codex reads hook config from .codex/hooks.json. We register a Bash matcher
    hook — Codex currently only exposes Bash as a hookable tool. File-write
    detection within Bash commands is a future improvement.

    Args:
        port: Port the Detent proxy is listening on (default 7070).

    Returns:
        True if the hook was added or was already present, False on error.
    """
    if not (1 <= port <= 65535):
        raise ValueError(f"port must be 1-65535, got {port!r}")

    hooks_path = Path(".codex") / "hooks.json"

    project_root = Path.cwd().resolve()
    try:
        resolved = hooks_path.parent.resolve()
    except OSError:
        resolved = hooks_path.parent
    if not resolved.is_relative_to(project_root):
        logger.error("Hooks path %s escapes project root; refusing to write", resolved)
        return False

    hook_command = f"curl -s -X POST http://127.0.0.1:{port}/hooks/codex" f" -H 'Content-Type: application/json' -d @-"
    detent_hook = {"type": "command", "command": hook_command}

    hooks_data: dict[str, Any] = {}
    if hooks_path.exists():
        try:
            hooks_data = json.loads(hooks_path.read_text())
        except (json.JSONDecodeError, OSError) as e:
            logger.warning("Could not read %s: %s", hooks_path, e)
            return False

    hooks: dict[str, Any] = hooks_data.setdefault("hooks", {})
    pretool_entries: list[dict[str, Any]] = hooks.setdefault("PreToolUse", [])

    for entry in pretool_entries:
        for h in entry.get("hooks", []):
            if "/hooks/codex" in h.get("command", ""):
                logger.debug("Detent codex hook already present in %s; skipping", hooks_path)
                return True

    pretool_entries.append({"matcher": "Bash", "hooks": [detent_hook]})
    hooks_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        hooks_path.write_text(json.dumps(hooks_data, indent=2) + "\n")
    except OSError as e:
        logger.warning("Could not write %s: %s", hooks_path, e)
        return False
    logger.info("Wrote Detent hook to %s", hooks_path)
    return True


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
