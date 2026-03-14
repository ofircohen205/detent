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

"""CLI package for Detent.

Imports main from app, then all command modules to trigger @main.command()
registration as side effects.

Re-exports all public names so that existing imports of the form
    from detent.cli import X
and patch targets of the form
    patch("detent.cli.X")
continue to work without modification.
"""

from __future__ import annotations

# Third-party names that tests patch via "detent.cli.<Name>"
from detent.checkpoint.engine import CheckpointEngine  # noqa: F401
from detent.pipeline.pipeline import VerificationPipeline  # noqa: F401

# 2. Command modules — register themselves on main as a side effect
from . import config, init, rollback, run, status  # noqa: F401

# 1. Click group — must be first
from .app import main  # noqa: F401

# 3. Helper re-exports so `from detent.cli import X` keeps working
from .init import init_interactive
from .rollback import do_rollback
from .run import run_file
from .session import SessionManager
from .status import show_status
from .utils import _policy_allows, console, create_session_dir, detect_agent, logger

__all__ = [
    "main",
    # command modules (imported for side-effect registration)
    "config",
    "init",
    "rollback",
    "run",
    "status",
    # helpers
    "SessionManager",
    "_policy_allows",
    "console",
    "create_session_dir",
    "detect_agent",
    "logger",
    "init_interactive",
    "run_file",
    "show_status",
    "do_rollback",
    # patched third-party names
    "CheckpointEngine",
    "VerificationPipeline",
]
