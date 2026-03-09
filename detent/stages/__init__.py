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

"""Verification stages — composable checks for the pipeline."""

from __future__ import annotations

from detent.stages.base import VerificationStage
from detent.stages.lint import LintStage
from detent.stages.syntax import SyntaxStage
from detent.stages.tests import TestsStage
from detent.stages.typecheck import TypecheckStage

STAGE_REGISTRY: dict[str, type[VerificationStage]] = {
    "syntax": SyntaxStage,
    "lint": LintStage,
    "typecheck": TypecheckStage,
    "tests": TestsStage,
}

__all__ = [
    "LintStage",
    "STAGE_REGISTRY",
    "SyntaxStage",
    "TestsStage",
    "TypecheckStage",
    "VerificationStage",
]
