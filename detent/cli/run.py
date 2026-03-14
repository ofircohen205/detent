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

"""run_file() helper and the 'run' CLI command."""

from __future__ import annotations

import asyncio
import copy
import json
import logging
from pathlib import Path
from typing import Any
from uuid import uuid4

import click

from detent.checkpoint.engine import CheckpointEngine
from detent.config import DetentConfig
from detent.pipeline.pipeline import VerificationPipeline
from detent.schema import ActionType, AgentAction, RiskLevel

from .app import main
from .session import SessionManager
from .utils import _policy_allows, console

logger = logging.getLogger(__name__)

_KNOWN_STAGES = frozenset({"syntax", "lint", "typecheck", "tests"})


async def run_file(
    file_path: str,
    config: DetentConfig,
    session: dict[str, Any],
    dry_run: bool = False,
    stage_filter: tuple[str, ...] = (),
    json_mode: bool = False,
) -> bool:
    """Execute verification pipeline for a file.

    Args:
        file_path: Path to file to verify.
        config: DetentConfig instance.
        session: Session dictionary.
        dry_run: If True, skip SAVEPOINT creation and rollback.
        stage_filter: If non-empty, run only these named stages (overrides config).
        json_mode: If True, emit JSON to stdout instead of Rich output.

    Returns:
        True if passed, False if failed.
    """
    path = Path(file_path).resolve()

    if not path.exists():
        raise click.ClickException(f"File not found: {file_path}")

    if stage_filter:
        unknown = set(stage_filter) - _KNOWN_STAGES
        if unknown:
            raise click.ClickException(
                f"Unknown stage: {', '.join(sorted(unknown))}. " f"Available: {', '.join(sorted(_KNOWN_STAGES))}"
            )
        config = copy.deepcopy(config)
        for stage in config.pipeline.stages:
            stage.enabled = stage.name in stage_filter

    checkpoint_engine = CheckpointEngine()
    pipeline = VerificationPipeline.from_config(config)
    mgr = SessionManager()

    ref = f"chk_before_write_{len(session['checkpoints']):03d}"

    if not dry_run:
        try:
            await checkpoint_engine.savepoint(ref, [str(path)])
        except Exception as e:
            logger.error(f"Failed to create checkpoint: {e}")
            raise click.ClickException(f"Checkpoint creation failed: {e}") from e
        mgr.add_checkpoint(session, ref, str(path), "created")

    content = path.read_text()
    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent=session.get("agent", "cli"),
        tool_name="Write",
        tool_input={"file_path": str(path), "content": content},
        tool_call_id=f"tool_{uuid4().hex[:8]}",
        session_id=session["session_id"],
        checkpoint_ref=ref if not dry_run else "dry_run",
        risk_level=RiskLevel.MEDIUM,
    )

    if not json_mode:
        console.print(f"\n[cyan]🔍 Running verification pipeline for {file_path}[/cyan]\n")
    result = await pipeline.run(action)

    if json_mode:
        output = {
            "passed": result.passed,
            "stage": result.stage,
            "findings": [
                {
                    "severity": finding.severity,
                    "file": finding.file,
                    "line": finding.line,
                    "column": finding.column,
                    "message": finding.message,
                    "code": finding.code,
                    "fix_suggestion": finding.fix_suggestion,
                }
                for finding in result.findings
            ],
            "checkpoint_ref": ref if not dry_run else None,
            "dry_run": dry_run,
        }
        click.echo(json.dumps(output))
        return result.passed

    if result.passed:
        console.print("[green]✅ All stages passed[/green]")
        if not dry_run:
            console.print(f"[cyan]Checkpoint: {ref}[/cyan]")
        return True

    console.print(f"[red]❌ Pipeline failed at {result.stage}[/red]\n")
    for finding in result.findings:
        severity_color = "red" if finding.severity == "error" else "yellow"
        console.print(
            f"[{severity_color}]{finding.severity.upper()}[/{severity_color}] "
            f"{finding.file}:{finding.line} {finding.message}"
        )
        if finding.fix_suggestion:
            console.print(f"  [cyan]→ {finding.fix_suggestion}[/cyan]")
    console.print()

    if _policy_allows(result, config.policy):
        console.print(f"[yellow]⚠ Policy allows proceeding (policy={config.policy})[/yellow]\n")
        return True

    if dry_run:
        console.print("[yellow]⚠ Dry run — skipping rollback[/yellow]\n")
        return False

    console.print(f"[yellow]🔄 Rolling back to {ref}[/yellow]\n")
    try:
        await checkpoint_engine.rollback(ref)
        mgr.update_checkpoint_status(session, ref, "rolled_back")
        mgr.save(session)
    except Exception as e:
        logger.error(f"Rollback failed: {e}")
        mgr.update_checkpoint_status(session, ref, "rollback_failed")
        mgr.save(session)
        raise click.ClickException(f"Rollback failed: {e}") from e

    return False


@main.command()
@click.argument("file_path")
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Run pipeline without creating checkpoint or rolling back",
)
@click.option(
    "--stage",
    "stages",
    multiple=True,
    help="Run only these stages (repeatable; overrides detent.yaml)",
)
@click.option("--json", "json_mode", is_flag=True, default=False, help="Output results as JSON")
@click.pass_context
def run(
    ctx: click.Context,
    file_path: str,
    dry_run: bool,
    stages: tuple[str, ...],
    json_mode: bool,
) -> None:
    """Verify a file through the full pipeline."""
    try:
        config_path = ctx.obj.get("config_path") if ctx.obj else None
        mgr = SessionManager()
        session = mgr.load_or_create()
        mgr.save(session)
        config = DetentConfig.load(path=config_path)
        result = asyncio.run(
            run_file(
                file_path,
                config,
                session,
                dry_run=dry_run,
                stage_filter=stages,
                json_mode=json_mode,
            )
        )
        raise SystemExit(0 if result else 1)
    except click.ClickException:
        raise
    except Exception as e:
        logger.error(f"Run failed: {e}")
        raise click.ClickException(str(e)) from e
