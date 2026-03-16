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

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings

# Configuration files for each language
ESLINT_CONFIG_FILES: tuple[str, ...] = (
    "eslint.config.js",
    "eslint.config.mjs",
    "eslint.config.cjs",
    ".eslintrc.js",
    ".eslintrc.cjs",
    ".eslintrc.json",
    ".eslintrc.yaml",
    ".eslintrc.yml",
)
TS_CONFIG_FILENAME: str = "tsconfig.json"


class LanguageSettings(BaseSettings):
    """Language-specific constants shared across lint/typecheck/test stages."""

    # File extensions for each language
    python_extensions: frozenset[str] = frozenset({".py"})
    js_extensions: frozenset[str] = frozenset({".js", ".jsx", ".mjs", ".cjs"})
    ts_extensions: frozenset[str] = frozenset({".ts", ".tsx"})
    go_extensions: frozenset[str] = frozenset({".go"})
    rust_extensions: frozenset[str] = frozenset({".rs"})

    # Configuration files for each language
    eslint_config_files: tuple[str, ...] = ESLINT_CONFIG_FILES
    ts_config_filename: str = TS_CONFIG_FILENAME

    @property
    def extension_map(self) -> dict[str, str]:
        """Mapping of file extensions to language names."""
        mapping = {}
        for ext in self.python_extensions:
            mapping[ext] = "python"
        for ext in self.js_extensions:
            mapping[ext] = "javascript"
        for ext in self.ts_extensions:
            mapping[ext] = "typescript"
        for ext in self.go_extensions:
            mapping[ext] = "go"
        for ext in self.rust_extensions:
            mapping[ext] = "rust"
        return mapping


@lru_cache
def get_language_settings() -> LanguageSettings:
    return LanguageSettings()


language_settings = get_language_settings()

# Pre-compute once from the singleton — avoids rebuilding the dict on every detect_language() call.
_EXTENSION_MAP: dict[str, str] = language_settings.extension_map


def detect_language(file_path: str | Path | None) -> str:
    """Detect language from file extension. Returns 'unknown' for unrecognized types."""
    if not file_path:
        return "unknown"
    suffix = Path(file_path).suffix.lower()
    return _EXTENSION_MAP.get(suffix, "unknown")
