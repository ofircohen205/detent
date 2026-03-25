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

"""init_interactive() helper and the 'init' CLI command."""

from __future__ import annotations

from pathlib import Path

import click
import structlog
import yaml

from detent.config import DetentConfig, PipelineConfig, ProxyConfig, StageConfig

from .app import main
from .utils import console, create_session_dir, detect_agent

logger: structlog.stdlib.BoundLogger = structlog.get_logger()


def init_interactive() -> None:
    """Interactive setup wizard for detent.yaml."""
    console.print("\n[cyan]✨ Detent Configuration Wizard[/cyan]\n")

    # Detect agent
    detected_agent = detect_agent()
    console.print(f"Detected agent: [yellow]{detected_agent}[/yellow]")

    agent_choice = click.prompt(
        "Is this correct?",
        type=click.Choice(["Y", "n"], case_sensitive=False),
        default="Y",
    )

    if agent_choice == "n":
        agent = click.prompt(
            "Select agent",
            type=click.Choice(["claude-code", "langgraph", "cursor", "aider"], case_sensitive=False),
            default="claude-code",
        )
    else:
        agent = detected_agent

    # Policy selection
    console.print("\nSelect policy profile:")
    console.print("  1. [bold]strict[/bold]   - all stages enabled, any finding blocks")
    console.print("  2. [bold]standard[/bold] - P0 stages enabled, warnings allowed")
    console.print("  3. [bold]permissive[/bold] - syntax only, others as warnings")

    policy_choice = click.prompt("Enter choice", type=click.Choice(["1", "2", "3"]), default="2")
    policy_map = {"1": "strict", "2": "standard", "3": "permissive"}
    policy = policy_map[policy_choice]

    # Optional settings
    parallel = click.confirm("Enable parallel execution?", default=False)
    fail_fast = click.confirm("Enable fail-fast?", default=True)

    # Create config
    stages = [
        StageConfig(name="syntax", enabled=True),
        StageConfig(name="lint", enabled=True),
        StageConfig(name="typecheck", enabled=True, timeout=30),
        StageConfig(name="tests", enabled=True, timeout=60),
        StageConfig(
            name="security",
            enabled=True,
            timeout=30,
            options={
                "semgrep": {"enabled": True, "rulesets": ["p/python", "p/owasp-top-ten"]},
                "bandit": {"enabled": True, "confidence": "low"},
            },
        ),
    ]

    config = DetentConfig(
        agent=agent,
        policy=policy,
        proxy=ProxyConfig(host="127.0.0.1", port=7070),
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
    console.print("[cyan]Ready to run: detent run <file>[/cyan]\n")


def init_non_interactive(force: bool = False) -> None:
    """Non-interactive setup: write defaults without prompts."""
    config_file = Path("detent.yaml")
    if config_file.exists() and not force:
        raise click.ClickException("detent.yaml already exists. Use --force to overwrite.")

    agent = detect_agent()
    stages = [
        StageConfig(name="syntax", enabled=True),
        StageConfig(name="lint", enabled=True),
        StageConfig(name="typecheck", enabled=True, timeout=30),
        StageConfig(name="tests", enabled=True, timeout=60),
        StageConfig(
            name="security",
            enabled=True,
            timeout=30,
            options={
                "semgrep": {"enabled": True, "rulesets": ["p/python", "p/owasp-top-ten"]},
                "bandit": {"enabled": True, "confidence": "low"},
            },
        ),
    ]
    config = DetentConfig(
        agent=agent,
        policy="standard",
        proxy=ProxyConfig(host="127.0.0.1", port=7070),
        pipeline=PipelineConfig(parallel=False, fail_fast=True, stages=stages),
    )
    with open("detent.yaml", "w") as f:
        yaml.dump(config.model_dump(), f, default_flow_style=False)
    create_session_dir()
    console.print("[green]✓ Created detent.yaml[/green]")
    console.print("[green]✓ Created .detent/session/[/green]")


@main.command()
@click.option(
    "--non-interactive",
    is_flag=True,
    default=False,
    help="Write defaults without prompts (suitable for CI)",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Overwrite existing detent.yaml",
)
@click.pass_context
def init(ctx: click.Context, non_interactive: bool, force: bool) -> None:
    """Initialize Detent in this project."""
    try:
        if non_interactive:
            init_non_interactive(force=force)
        else:
            init_interactive()
    except click.ClickException:
        raise
    except Exception as e:
        logger.error(f"Init failed: {e}")
        raise click.ClickException(str(e)) from e
