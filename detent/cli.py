"""CLI module for Detent.

Provides session management, command handlers, and Rich output formatting.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import click

from detent import __version__

logger = logging.getLogger(__name__)


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


@click.group()
@click.version_option(version=__version__)
def main() -> None:
    """Detent: A verification runtime for AI coding agents.

    Detent intercepts file writes, runs them through a configurable verification
    pipeline, and rolls back atomically on failure.
    """
    pass


if __name__ == "__main__":
    main()
