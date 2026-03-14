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
import logging

import click

from detent.checkpoint.engine import CheckpointEngine

from .app import main
from .session import SessionManager
from .utils import console

logger = logging.getLogger(__name__)


async def do_rollback(ref: str) -> None:
    """Restore file to checkpoint.

    Args:
        ref: Checkpoint reference
    """
    mgr = SessionManager()
    session = mgr.load_or_create()

    checkpoint = mgr.get_checkpoint(session, ref)

    if checkpoint is None:
        available = [c["ref"] for c in session["checkpoints"]]
        console.print(f"[red]✗ Checkpoint not found: {ref}[/red]")
        if available:
            console.print(f"[yellow]Available: {', '.join(available)}[/yellow]")
        raise click.ClickException(f"Checkpoint not found: {ref}")

    console.print(f"\n[cyan]🔄 Rolling back to {ref} ({checkpoint['file']})[/cyan]\n")

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
@click.pass_context
@click.argument("checkpoint_ref")
def rollback(ctx: click.Context, checkpoint_ref: str) -> None:
    """Restore a file to a checkpoint."""
    try:
        asyncio.run(do_rollback(checkpoint_ref))
    except click.ClickException:
        raise
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        raise click.ClickException(str(e)) from e
