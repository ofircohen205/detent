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

"""Language-specific constants shared across lint/typecheck/test stages."""

from __future__ import annotations

from typing import Any, Final

try:
    import tree_sitter_javascript as tsjavascript
    import tree_sitter_python as tspython
    import tree_sitter_typescript as tstypescript
    from tree_sitter import Language
except ImportError:
    tsjavascript = None
    tspython = None
    tstypescript = None
    Language = Any

PYTHON_EXTENSIONS: Final[frozenset[str]] = frozenset({".py"})
JS_TS_EXTENSIONS: Final[frozenset[str]] = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})

ESLINT_CONFIG_FILES: Final[tuple[str, ...]] = (
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.json",
    ".eslintrc.yaml",
    ".eslintrc.yml",
)

TS_CONFIG_FILENAME: Final[str] = "tsconfig.json"
TS_EXTENSIONS: Final[frozenset[str]] = frozenset({".ts", ".tsx"})

if tsjavascript and tspython and tstypescript and Language:
    TREE_SITTER_LANGUAGE_MAP: Final[dict[str, Language]] = {
        ".py": Language(tspython.language()),
        ".js": Language(tsjavascript.language()),
        ".jsx": Language(tsjavascript.language()),
        ".ts": Language(tstypescript.language_typescript()),
        ".tsx": Language(tstypescript.language_tsx()),
    }
else:
    TREE_SITTER_LANGUAGE_MAP: Final[dict[str, Language]] = {}
