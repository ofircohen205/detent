"""CLI module for Detent.

Provides session management, command handlers, and Rich output formatting.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import click
import yaml
from rich.console import Console
from rich.prompt import Confirm, Prompt
from rich.table import Table

from detent import __version__
from detent.checkpoint.engine import CheckpointEngine
from detent.config import DetentConfig, PipelineConfig, StageConfig
from detent.pipeline.pipeline import VerificationPipeline
from detent.pipeline.result import VerificationResult
from detent.schema import ActionType, AgentAction, RiskLevel

logger = logging.getLogger(__name__)
console = Console()


class SessionManager:
    """Manages CLI session state (distinct from proxy.SessionManager)."""

    def __init__(self, session_dir: Path | str | None = None) -> None:
        """Initialize session manager.

        Args:
            session_dir: Directory to store session state (default: .detent/session)
        """
        self.session_dir = Path(session_dir or ".detent/session")

    def load_or_create(self) -> dict[str, Any]:
        """Load existing session or create new one.

        Returns:
            Session dictionary
        """
        session_file = self.session_dir / "default.json"

        if session_file.exists():
            try:
                return json.loads(session_file.read_text())
            except json.JSONDecodeError as e:
                logger.warning(f"Session file corrupted: {e}, creating new session")
                return self._create_new_session()

        return self._create_new_session()

    def _create_new_session(self) -> dict[str, Any]:
        """Create a new session."""
        return {
            "session_id": f"sess_{uuid4().hex[:12]}",
            "active": True,
            "started_at": datetime.now(UTC).isoformat(),
            "last_updated": datetime.now(UTC).isoformat(),
            "checkpoints": [],
        }

    def save(self, session: dict[str, Any]) -> None:
        """Persist session to disk.

        Args:
            session: Session dictionary to save
        """
        self.session_dir.mkdir(parents=True, exist_ok=True)
        session_file = self.session_dir / "default.json"
        session_file.write_text(json.dumps(session, indent=2))
        logger.debug(f"Session saved to {session_file}")

    def add_checkpoint(
        self,
        session: dict[str, Any],
        ref: str,
        file: str,
        status: str = "created",
    ) -> None:
        """Track checkpoint in session state.

        Args:
            session: Session dictionary
            ref: Checkpoint reference (e.g., "chk_before_write_000")
            file: File path associated with checkpoint
            status: Checkpoint status (created, rolled_back, restored, rollback_failed)
        """
        session["checkpoints"].append(
            {
                "ref": ref,
                "file": file,
                "created_at": datetime.now(UTC).isoformat(),
                "status": status,
            }
        )
        session["last_updated"] = datetime.now(UTC).isoformat()

    def get_checkpoint(
        self, session: dict[str, Any], ref: str
    ) -> dict[str, Any] | None:
        """Retrieve checkpoint by reference.

        Args:
            session: Session dictionary
            ref: Checkpoint reference

        Returns:
            Checkpoint dictionary or None if not found
        """
        for chk in session["checkpoints"]:
            if chk["ref"] == ref:
                return chk
        return None

    def update_checkpoint_status(
        self, session: dict[str, Any], ref: str, status: str
    ) -> None:
        """Update checkpoint status.

        Args:
            session: Session dictionary
            ref: Checkpoint reference
            status: New status
        """
        for chk in session["checkpoints"]:
            if chk["ref"] == ref:
                chk["status"] = status
                session["last_updated"] = datetime.now(UTC).isoformat()
                break


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


def init_interactive() -> None:
    """Interactive setup wizard for detent.yaml."""
    console.print("\n[cyan]✨ Detent Configuration Wizard[/cyan]\n")

    # Detect agent
    detected_agent = detect_agent()
    console.print(f"Detected agent: [yellow]{detected_agent}[/yellow]")

    agent_choice = Prompt.ask(
        "Is this correct?",
        choices=["Y", "n"],
        default="Y",
    )

    if agent_choice == "n":
        agent = Prompt.ask(
            "Select agent",
            choices=["claude-code", "langgraph", "cursor", "aider"],
            default="claude-code",
        )
    else:
        agent = detected_agent

    # Policy selection
    console.print("\nSelect policy profile:")
    console.print("  1. [bold]strict[/bold]   - all stages enabled, any finding blocks")
    console.print("  2. [bold]standard[/bold] - P0 stages enabled, warnings allowed")
    console.print("  3. [bold]permissive[/bold] - syntax only, others as warnings")

    policy_choice = Prompt.ask("Enter choice", choices=["1", "2", "3"], default="2")
    policy_map = {"1": "strict", "2": "standard", "3": "permissive"}
    policy = policy_map[policy_choice]

    # Optional settings
    parallel = Confirm.ask("Enable parallel execution?", default=False)
    fail_fast = Confirm.ask("Enable fail-fast?", default=True)

    # Create config
    stages = [
        StageConfig(name="syntax", enabled=True),
        StageConfig(name="lint", enabled=True),
        StageConfig(name="typecheck", enabled=True, timeout=30),
        StageConfig(name="tests", enabled=True, timeout=60),
    ]

    config = DetentConfig(
        agent=agent,
        policy=policy,
        proxy={"host": "127.0.0.1", "port": 7070},
        pipeline=PipelineConfig(
            parallel=parallel,
            fail_fast=fail_fast,
            stages=stages,
        ),
    )

    # Write detent.yaml
    with open("detent.yaml", "w") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False)

    # Create session directory
    create_session_dir()

    console.print("\n[green]✓ Created detent.yaml[/green]")
    console.print("[green]✓ Created .detent/session/[/green]")
    console.print(f"[cyan]Ready to run: detent run <file>[/cyan]\n")


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """Detent: A verification runtime for AI coding agents.

    Detent intercepts file writes, runs them through a configurable verification
    pipeline, and rolls back atomically on failure.
    """
    pass


@main.command()
def init() -> None:
    """Initialize Detent in this project."""
    try:
        init_interactive()
    except Exception as e:
        logger.error(f"Init failed: {e}")
        raise click.ClickException(str(e))


if __name__ == "__main__":
    main()
