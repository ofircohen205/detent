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

"""SyntaxStage — tree-sitter Python syntax validation.

Parses content in-memory. No temp files, no subprocess — fast.
Reports ERROR and MISSING nodes as findings with line/column numbers.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import TYPE_CHECKING

from tree_sitter import Parser

from detent.config.languages import TREE_SITTER_LANGUAGE_MAP
from detent.pipeline.result import Finding, VerificationResult
from detent.stages.base import VerificationStage

if TYPE_CHECKING:
    from tree_sitter import Node

    from detent.schema import AgentAction

logger = logging.getLogger(__name__)

_LANGUAGE_MAP = TREE_SITTER_LANGUAGE_MAP
_SUPPORTED_EXTENSIONS = frozenset(_LANGUAGE_MAP.keys())


class SyntaxStage(VerificationStage):
    """Validates Python syntax using tree-sitter.

    Parses proposed content in-memory. Finds all ERROR and MISSING nodes
    in the AST and reports them as error Findings.
    """

    name = "syntax"

    def supports_language(self, lang: str) -> bool:
        """Return True only for Python."""
        return lang in {"python", "py", "javascript", "typescript"}

    async def _run(self, action: AgentAction) -> VerificationResult:
        """Parse proposed content and return any syntax error findings."""
        start = time.perf_counter()

        file_path = action.file_path or ""
        content = action.content or ""

        ext = Path(file_path).suffix.lower()
        language = _LANGUAGE_MAP.get(ext)
        if language is None:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.debug("[syntax] skipping unsupported extension: %s", ext)
            return VerificationResult(
                stage=self.name,
                passed=True,
                findings=[],
                duration_ms=duration_ms,
                metadata={"skipped": True, "reason": f"Unsupported extension: {ext}"},
            )

        parser = Parser(language=language)
        tree = parser.parse(content.encode("utf-8"))

        findings: list[Finding] = []
        self._collect_errors(tree.root_node, file_path, findings)

        duration_ms = (time.perf_counter() - start) * 1000

        return VerificationResult(
            stage=self.name,
            passed=len(findings) == 0,
            findings=findings,
            duration_ms=duration_ms,
            metadata={"node_count": tree.root_node.child_count},
        )

    def _collect_errors(self, root: Node, file_path: str, findings: list[Finding]) -> None:
        """Walk the AST iteratively and collect ERROR / MISSING nodes.

        Uses an explicit stack instead of recursion to avoid hitting Python's
        recursion limit on very deep or large ASTs from AI-generated code.

        Uses node.is_error and node.is_missing (the correct tree-sitter API) rather than
        comparing node.type to the strings "ERROR" or "MISSING". A missing token has its
        expected type (e.g. ')') with is_missing=True, not type="MISSING".
        """
        stack = [root]
        while stack:
            node = stack.pop()
            if node.is_error or node.is_missing:
                row, col = node.start_point
                findings.append(
                    Finding(
                        severity="error",
                        file=file_path,
                        line=row + 1,  # tree-sitter is 0-indexed; Finding uses 1-indexed
                        column=col + 1,
                        message=f"Syntax error: unexpected {'token' if node.is_error and not node.is_missing else 'token (missing)'}",
                        code="syntax-error",
                        stage=self.name,
                        fix_suggestion=None,
                    )
                )
            stack.extend(node.children)
