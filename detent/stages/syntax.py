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

"""SyntaxStage — multi-language tree-sitter syntax validation.

Grammars are loaded at import time with per-grammar try/except so a missing
optional grammar does not break the stage for other languages.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from tree_sitter import Language, Parser

from detent.pipeline.result import Finding, VerificationResult
from detent.stages.base import VerificationStage, _detect_language

if TYPE_CHECKING:
    from tree_sitter import Node

    from detent.schema import AgentAction

logger = logging.getLogger(__name__)

# _GRAMMAR_MAP: language name -> tree-sitter Language
# Missing grammars are silently absent; supports_language() returns False for them.
_GRAMMAR_MAP: dict[str, Language] = {}

try:
    import tree_sitter_python as _tspy

    _GRAMMAR_MAP["python"] = Language(_tspy.language())  # type: ignore[call-arg, arg-type]
except (ImportError, Exception):
    pass

try:
    import tree_sitter_javascript as _tsjs

    _GRAMMAR_MAP["javascript"] = Language(_tsjs.language())  # type: ignore[call-arg, arg-type]
except (ImportError, Exception):
    pass

try:
    import tree_sitter_typescript as _tsts

    _GRAMMAR_MAP["typescript"] = Language(_tsts.language_typescript())  # type: ignore[call-arg, arg-type]
except (ImportError, Exception):
    pass

try:
    import tree_sitter_go as _tsgo

    _GRAMMAR_MAP["go"] = Language(_tsgo.language())  # type: ignore[call-arg, arg-type]
except (ImportError, Exception):
    pass

try:
    import tree_sitter_rust as _tsrust

    _GRAMMAR_MAP["rust"] = Language(_tsrust.language())  # type: ignore[call-arg, arg-type]
except (ImportError, Exception):
    pass


class SyntaxStage(VerificationStage):
    """Validates syntax using tree-sitter grammars."""

    name = "syntax"

    def supports_language(self, lang: str) -> bool:
        return lang in _GRAMMAR_MAP

    async def _run(self, action: AgentAction) -> VerificationResult:
        """Parse proposed content and return any syntax error findings."""
        start = time.perf_counter()
        file_path = action.file_path or ""
        content = action.content or ""

        lang = _detect_language(file_path)
        grammar = _GRAMMAR_MAP.get(lang)
        if grammar is None:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.debug("[syntax] skipping unsupported language: %s", lang)
            return VerificationResult(
                stage=self.name,
                passed=True,
                findings=[],
                duration_ms=duration_ms,
                metadata={"skipped": True, "reason": f"Unsupported language: {lang}"},
            )

        parser = Parser(grammar)  # type: ignore[call-arg]
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
        """Walk AST iteratively; collect ERROR / MISSING nodes.

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
                        line=row + 1,
                        column=col + 1,
                        message=f"Syntax error: unexpected {'token' if node.is_error and not node.is_missing else 'token (missing)'}",
                        code="syntax-error",
                        stage=self.name,
                        fix_suggestion=None,
                    )
                )
            stack.extend(node.children)
