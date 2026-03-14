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

"""Config subcommand group for detent CLI."""

from __future__ import annotations

from pathlib import Path

import click
import yaml

from detent.config import DetentConfig

from .app import main
from .utils import console


@main.group()
@click.pass_context
def config(ctx: click.Context) -> None:
    """Manage Detent configuration."""
    pass


@config.command(name="validate")
@click.pass_context
def config_validate(ctx: click.Context) -> None:
    """Validate detent.yaml, print errors, exit 1 if invalid."""
    config_path = ctx.obj.get("config_path") if ctx.obj else None
    try:
        if config_path and not Path(config_path).exists():
            console.print(f"[red]✗ Configuration invalid:[/red] File not found: {config_path}")
            raise SystemExit(1)
        cfg = DetentConfig.load(path=config_path)
        console.print("[green]✓ Configuration is valid[/green]")
        console.print(f"  policy={cfg.policy}, stages={len(cfg.pipeline.stages)}")
    except Exception as e:
        console.print(f"[red]✗ Configuration invalid:[/red] {e}")
        raise SystemExit(1) from e


@config.command(name="show")
@click.pass_context
def config_show(ctx: click.Context) -> None:
    """Pretty-print resolved configuration as YAML."""
    config_path = ctx.obj.get("config_path") if ctx.obj else None
    try:
        cfg = DetentConfig.load(path=config_path)
        click.echo(yaml.dump(cfg.model_dump(), default_flow_style=False))
    except Exception as e:
        console.print(f"[red]✗ Failed to load configuration:[/red] {e}")
        raise SystemExit(1) from e
