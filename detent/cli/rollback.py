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

"""do_rollback() helper and the 'rollback' CLI command."""

from __future__ import annotations

import asyncio

import click
import structlog

from detent.checkpoint.engine import CheckpointEngine

from .app import main
from .session import SessionManager
from .utils import console

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


async def do_rollback(
    ref: str | None,
    latest: bool = False,
    yes: bool = False,
) -> None:
    """Restore file to checkpoint.

    Args:
        ref: Checkpoint reference, or None when using --latest.
        latest: If True, roll back the most recent checkpoint.
        yes: Skip confirmation prompt.
    """
    mgr = SessionManager()
    session = mgr.load_or_create()

    if latest:
        created = [c for c in session["checkpoints"] if c["status"] == "created"]
        if not created:
            raise click.ClickException("No checkpoints to roll back")
        ref = created[-1]["ref"]

    if ref is None:
        raise click.ClickException("Specify a checkpoint ref or use --latest")

    checkpoint = mgr.get_checkpoint(session, ref)

    if checkpoint is None:
        available = [c["ref"] for c in session["checkpoints"]]
        console.print(f"[red]✗ Checkpoint not found: {ref}[/red]")
        if available:
            console.print(f"[yellow]Available: {', '.join(available)}[/yellow]")
        raise click.ClickException(f"Checkpoint not found: {ref}")

    console.print(f"\n[cyan]🔄 Rollback {ref} → {checkpoint['file']}[/cyan]")

    if not yes:
        confirmed = click.confirm(f"Restore {checkpoint['file']} to {ref}?", default=False)
        if not confirmed:
            console.print("Aborted")
            return

    checkpoint_engine = CheckpointEngine()
    try:
        await checkpoint_engine.rollback(ref)
        mgr.update_checkpoint_status(session, ref, "restored")
        mgr.save(session)
        console.print(f"[green]✓ Restored {checkpoint['file']} to {ref}[/green]\n")
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        mgr.update_checkpoint_status(session, ref, "rollback_failed")
        mgr.save(session)
        raise click.ClickException(f"Rollback failed: {e}") from e


@main.command()
@click.argument("checkpoint_ref", required=False, default=None)
@click.option(
    "--latest",
    is_flag=True,
    default=False,
    help="Roll back to the most recent checkpoint with status 'created'",
)
@click.option("--yes", "-y", is_flag=True, default=False, help="Skip confirmation prompt")
@click.pass_context
def rollback(ctx: click.Context, checkpoint_ref: str | None, latest: bool, yes: bool) -> None:
    """Restore a file to a checkpoint.

    Specify CHECKPOINT_REF or use --latest to select the most recent checkpoint.
    """
    if not checkpoint_ref and not latest:
        raise click.UsageError("Specify a CHECKPOINT_REF or use --latest")
    try:
        asyncio.run(do_rollback(ref=checkpoint_ref, latest=latest, yes=yes))
    except click.ClickException:
        raise
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        raise click.ClickException(str(e)) from e
