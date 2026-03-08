"""Detent CLI entry point.

This module implements the command-line interface for Detent, the verification runtime.
"""

import click


@click.group()
def main() -> None:
    """Detent: A verification runtime for AI coding agents.

    Detent intercepts file writes, runs them through a configurable verification
    pipeline, and rolls back atomically on failure.
    """
    pass


if __name__ == "__main__":
    main()
