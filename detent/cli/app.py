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

"""Click group definition for the Detent CLI."""

from __future__ import annotations

import logging

import click

from detent import __version__


@click.group()
@click.version_option(version=__version__)
@click.option("--verbose", "-v", is_flag=True, default=False, help="Enable debug logging")
@click.option(
    "--config",
    "config_path",
    default=None,
    envvar="DETENT_CONFIG",
    help="Path to detent.yaml (overrides DETENT_CONFIG env var)",
)
@click.pass_context
def main(ctx: click.Context, verbose: bool, config_path: str | None) -> None:
    """Detent: A verification runtime for AI coding agents.

    Detent intercepts file writes, runs them through a configurable verification
    pipeline, and rolls back atomically on failure.
    """
    ctx.ensure_object(dict)
    ctx.obj["config_path"] = config_path
    if verbose:
        logging.root.setLevel(logging.DEBUG)
