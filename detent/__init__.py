"""Detent — a verification runtime for AI coding agents.

Intercepts file writes, runs them through a configurable verification pipeline,
and rolls back atomically if the code fails.
"""

from __future__ import annotations

__version__ = "0.1.0"

# Public SDK exports will be available once the corresponding modules
# are implemented. For now, we define __all__ for documentation purposes.
__all__ = [
    "__version__",
]
