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

"""show_status() helper and the 'status' CLI command."""

from __future__ import annotations

import json
import logging

import click
from rich.table import Table

from .app import main
from .session import SessionManager
from .utils import console

logger = logging.getLogger(__name__)


def show_status(json_mode: bool = False, reset: bool = False) -> None:
    """Display active session and checkpoints.

    Args:
        json_mode: Output as JSON instead of Rich table.
        reset: Clear all session state after confirmation.
    """
    mgr = SessionManager()
    session = mgr.load_or_create()

    if reset:
        session_file = mgr.session_dir / "default.json"
        if not session_file.exists():
            console.print("[yellow]No session to reset.[/yellow]")
            return
        confirmed = click.confirm(
            "Reset session? This deletes all checkpoints.",
            default=False,
        )
        if confirmed:
            session_file.unlink()
            console.print("[green]✓ Session reset[/green]")
        else:
            console.print("Aborted")
        return

    if json_mode:
        click.echo(json.dumps(session, indent=2))
        return

    if not session["checkpoints"]:
        console.print("[yellow]No checkpoints yet. Run 'detent run <file>' first.[/yellow]")
        return

    table = Table(title=f"Detent Session {session['session_id']}")
    table.add_column("Checkpoint", style="cyan")
    table.add_column("File", style="magenta")
    table.add_column("Status", style="green")
    table.add_column("Stage", style="blue")
    table.add_column("Created", style="yellow")

    for chk in session["checkpoints"]:
        status_color = "green" if chk["status"] == "created" else "yellow"
        table.add_row(
            chk["ref"],
            chk["file"],
            f"[{status_color}]{chk['status']}[/{status_color}]",
            chk.get("stage", "-"),
            chk["created_at"],
        )

    console.print(table)


@main.command()
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output session state as JSON")
@click.option(
    "--reset",
    is_flag=True,
    default=False,
    help="Clear all session state (requires confirmation)",
)
@click.pass_context
def status(ctx: click.Context, json_mode: bool, reset: bool) -> None:
    """Show active session and checkpoints."""
    try:
        show_status(json_mode=json_mode, reset=reset)
    except click.ClickException:
        raise
    except Exception as e:
        logger.error(f"Status failed: {e}")
        raise click.ClickException(str(e)) from e
