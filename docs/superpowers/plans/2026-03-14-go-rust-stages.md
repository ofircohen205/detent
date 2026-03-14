# Go + Rust Stages Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add Go and Rust support to all four verification stages (syntax, lint, typecheck, tests) and refactor stage helpers into language-centric modules (`python.py`, `javascript.py`, `go.py`, `rust.py`).

**Architecture:** Each language gets a dedicated helper module exposing `async run_<tool>(file_path, content, stage_name, timeout) -> list[Finding]`. Stage files (`lint.py`, `typecheck.py`, `tests.py`) dispatch to these helpers based on `_detect_language(file_path)`. Go and Rust use a write-then-check pattern (file must exist on disk in the module/crate). Syntax uses tree-sitter with a language-name-keyed `_GRAMMAR_MAP` built at import time with per-grammar `try/except`.

**Tech Stack:** `tree-sitter-go`, `tree-sitter-rust`, `go vet`/`go build`/`go test -json`, `cargo clippy --message-format=json`/`cargo check --message-format=json`/`cargo test`

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `pyproject.toml` | Modify | Add `tree-sitter-go>=0.23,<1` and `tree-sitter-rust>=0.23,<1` |
| `detent/config/languages.py` | Modify | Add `GO_EXTENSIONS`, `RUST_EXTENSIONS`; remove `TREE_SITTER_LANGUAGE_MAP` (moved to syntax.py) |
| `detent/stages/syntax.py` | Modify | Language-name-keyed `_GRAMMAR_MAP`; add Go + Rust; fix `"py"` dead code in `supports_language()` |
| `detent/stages/python.py` | Create | `run_ruff()`, `run_mypy()`, `run_pytest()` extracted from lint/typecheck/tests |
| `detent/stages/javascript.py` | Create | `run_eslint()`, `run_tsc()`, `run_jest()` consolidated from lint_js/typecheck_js/tests_js |
| `detent/stages/go.py` | Create | `find_module_root()`, `run_vet()`, `run_build()`, `run_test()` |
| `detent/stages/rust.py` | Create | `find_crate_root()`, `run_clippy()`, `run_check()`, `run_test()` |
| `detent/stages/lint.py` | Modify | Language dispatch to helpers; add Go/Rust; remove extension guard; update `supports_language()` |
| `detent/stages/typecheck.py` | Modify | Language dispatch to helpers; add Go/Rust; fix `"py"` dead code; update `supports_language()` |
| `detent/stages/tests.py` | Modify | Language dispatch to helpers; add Go/Rust; remove `.py` guard in `_find_test_files()` |
| `detent/stages/lint_js.py` | Delete | Superseded by `javascript.py` |
| `detent/stages/typecheck_js.py` | Delete | Superseded by `javascript.py` |
| `detent/stages/tests_js.py` | Delete | Superseded by `javascript.py` |
| `tests/unit/test_go_stage.py` | Create | Unit tests for `go.py` helpers |
| `tests/unit/test_rust_stage.py` | Create | Unit tests for `rust.py` helpers |
| `tests/integration/test_go_integration.py` | Create | Integration tests: known-bad Go files through stages |
| `tests/integration/test_rust_integration.py` | Create | Integration tests: known-bad Rust files through stages |

---

## Chunk 1: Dependencies + Config + Syntax

### Task 1: Add tree-sitter-go and tree-sitter-rust dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dependencies**

In `pyproject.toml`, in the `[project] dependencies` list, add after the existing tree-sitter entries:

```toml
"tree-sitter-go>=0.23,<1",
"tree-sitter-rust>=0.23,<1",
```

- [ ] **Step 2: Install and lock**

```
uv sync --all-extras --dev
```

Expected: resolves and installs `tree-sitter-go` and `tree-sitter-rust` packages.

- [ ] **Step 3: Smoke-test imports**

```
uv run python -c "import tree_sitter_go; import tree_sitter_rust; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```
git add pyproject.toml uv.lock
git commit -m "chore: add tree-sitter-go and tree-sitter-rust deps"
```

---

### Task 2: Update config/languages.py

**Files:**
- Modify: `detent/config/languages.py`

- [ ] **Step 1: Add Go/Rust extension constants; remove TREE_SITTER_LANGUAGE_MAP**

`TREE_SITTER_LANGUAGE_MAP` is moving to `syntax.py`. Extension constants stay here since lint/typecheck/tests need them.

Replace `detent/config/languages.py` content with:

```python
"""Language-specific constants shared across lint/typecheck/test stages."""

from __future__ import annotations

from typing import Final

PYTHON_EXTENSIONS: Final[frozenset[str]] = frozenset({".py"})
JS_TS_EXTENSIONS: Final[frozenset[str]] = frozenset({".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"})
GO_EXTENSIONS: Final[frozenset[str]] = frozenset({".go"})
RUST_EXTENSIONS: Final[frozenset[str]] = frozenset({".rs"})

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
```

(Keep the Apache license header at the top of the file.)

- [ ] **Step 2: Verify TREE_SITTER_LANGUAGE_MAP only used in syntax.py**

```
grep -r "TREE_SITTER_LANGUAGE_MAP" detent/ --include="*.py"
```

Expected: only `detent/stages/syntax.py` — that file gets rewritten in Task 3.

- [ ] **Step 3: Run unit tests (excluding syntax) to confirm no breakage**

```
uv run pytest tests/unit/ -q --ignore=tests/unit/test_syntax_stage.py 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 4: Commit**

```
git add detent/config/languages.py
git commit -m "refactor: add Go/Rust extension constants; move TREE_SITTER_LANGUAGE_MAP to syntax.py"
```

---

### Task 3: Refactor syntax.py — language-name keyed _GRAMMAR_MAP + Go + Rust

**Files:**
- Modify: `detent/stages/syntax.py`
- Modify: `tests/unit/test_syntax_stage.py`

- [ ] **Step 1: Write failing tests for Go/Rust support**

Add to `tests/unit/test_syntax_stage.py`:

```python
async def test_supports_go(stage: SyntaxStage) -> None:
    assert stage.supports_language("go") is True


async def test_supports_rust(stage: SyntaxStage) -> None:
    assert stage.supports_language("rust") is True


async def test_does_not_support_py_alias(stage: SyntaxStage) -> None:
    # Pipeline always sends "python", not "py"
    assert stage.supports_language("py") is False


async def test_valid_go_passes(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.go", content="package main\n\nfunc main() {}\n")
    result = await stage.run(action)
    assert result.passed
    assert result.findings == []


async def test_invalid_go_fails(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.go", content="package main\n\nfunc main( {\n")
    result = await stage.run(action)
    assert not result.passed
    assert len(result.findings) > 0


async def test_valid_rust_passes(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.rs", content="fn main() {}\n")
    result = await stage.run(action)
    assert result.passed
    assert result.findings == []


async def test_invalid_rust_fails(stage: SyntaxStage) -> None:
    action = make_action(file_path="/src/main.rs", content="fn main( {\n")
    result = await stage.run(action)
    assert not result.passed
    assert len(result.findings) > 0
```

- [ ] **Step 2: Run to verify they fail**

```
uv run pytest tests/unit/test_syntax_stage.py -q 2>&1 | tail -10
```

Expected: 7 new tests FAIL.

- [ ] **Step 3: Rewrite syntax.py with language-name keyed _GRAMMAR_MAP**

Replace `detent/stages/syntax.py` with:

```python
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
    _GRAMMAR_MAP["python"] = Language(_tspy.language())
except (ImportError, Exception):
    pass

try:
    import tree_sitter_javascript as _tsjs
    _GRAMMAR_MAP["javascript"] = Language(_tsjs.language())
except (ImportError, Exception):
    pass

try:
    import tree_sitter_typescript as _tsts
    _GRAMMAR_MAP["typescript"] = Language(_tsts.language_typescript())
except (ImportError, Exception):
    pass

try:
    import tree_sitter_go as _tsgo
    _GRAMMAR_MAP["go"] = Language(_tsgo.language())
except (ImportError, Exception):
    pass

try:
    import tree_sitter_rust as _tsrust
    _GRAMMAR_MAP["rust"] = Language(_tsrust.language())
except (ImportError, Exception):
    pass


class SyntaxStage(VerificationStage):
    """Validates syntax using tree-sitter grammars."""

    name = "syntax"

    def supports_language(self, lang: str) -> bool:
        return lang in _GRAMMAR_MAP

    async def _run(self, action: AgentAction) -> VerificationResult:
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

        parser = Parser(grammar)
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
        """Walk AST iteratively; collect ERROR / MISSING nodes."""
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
```

- [ ] **Step 4: Run all syntax tests**

```
uv run pytest tests/unit/test_syntax_stage.py -q 2>&1 | tail -10
```

Expected: all pass.

- [ ] **Step 5: Run full unit suite**

```
uv run pytest tests/unit/ -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 6: Commit**

```
git add detent/stages/syntax.py tests/unit/test_syntax_stage.py
git commit -m "feat: add Go and Rust grammar support to SyntaxStage"
```

---

## Chunk 2: Language Helper Modules (Refactor)

### Task 4: Create python.py — extract ruff, mypy, pytest helpers

**Files:**
- Create: `detent/stages/python.py`

Extract the ruff, mypy, and pytest logic from lint.py, typecheck.py, and tests.py into standalone async functions. Key changes:
- Add `stage_name: str` parameter to all functions (used in Finding.stage field and logging)
- Remove outer timing/VerificationResult construction (stays in the stage's `_run()`)
- `run_ruff` and `run_mypy`: `(file_path, content, stage_name, timeout) -> list[Finding]`
- `run_pytest`: `(file_path, stage_name, timeout) -> list[Finding]` (no `content`)

- [ ] **Step 1: Create `detent/stages/python.py`**

The file contains three sections: ruff, mypy, pytest. Extract the existing logic verbatim from the current stage files — do not change behavior. Add `stage_name` parameter everywhere `self.name` was used.

Key functions to implement:
- `run_ruff(file_path, content, stage_name, timeout) -> list[Finding]` — stdin pipe to ruff, parse JSON output
- `_parse_ruff_finding(raw, stage_name) -> Finding` — map ruff severity codes (W=warning, I=info, else=error)
- `run_mypy(file_path, content, stage_name, timeout) -> list[Finding]` — write temp .py file, run mypy --output=json, filter notes
- `_parse_mypy_finding(raw, original_path, stage_name) -> Finding`
- `run_pytest(file_path, stage_name, timeout) -> list[Finding]` — discover test files via `_find_test_files()`, run pytest
- `_find_test_files(file_path) -> list[Path]` — walk up 5 levels looking for `tests/test_{stem}.py`
- `_parse_pytest_failures(output, file_path, stage_name) -> list[Finding]` — parse `FAILED ` lines

Handle `FileNotFoundError` (tool not installed) and `TimeoutError` by returning warning findings — never raise.

- [ ] **Step 2: Verify it imports cleanly**

```
uv run python -c "from detent.stages import python; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```
git add detent/stages/python.py
git commit -m "feat: extract python.py language helper (ruff, mypy, pytest)"
```

---

### Task 5: Create javascript.py — consolidate lint_js, typecheck_js, tests_js

**Files:**
- Create: `detent/stages/javascript.py`

Consolidate the three existing helper files into one module. All internal logic stays identical; add `stage_name: str` parameter to each public function (matching the python.py interface).

- [ ] **Step 1: Create `detent/stages/javascript.py`**

Key functions:
- `run_eslint(file_path, content, stage_name, timeout) -> list[Finding]` — from lint_js.py
- `run_tsc(file_path, content, stage_name, timeout) -> list[Finding]` — from typecheck_js.py (content unused; tsc reads from disk)
- `run_jest(file_path, stage_name, timeout, tool_override=None) -> list[Finding]` — from tests_js.py
- Internal helpers: `_find_eslint_config()`, `_find_tsconfig()`, `_detect_js_runner()`, `_find_js_test_file()`, `_cleanup()`

Copy existing logic from lint_js.py, typecheck_js.py, tests_js.py verbatim; rename `run_js_tests` → `run_jest`; add `stage_name` parameter.

- [ ] **Step 2: Verify it imports cleanly**

```
uv run python -c "from detent.stages import javascript; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```
git add detent/stages/javascript.py
git commit -m "feat: consolidate JS/TS helpers into javascript.py"
```

---

### Task 6: Wire helpers into stages; delete old helpers

**Files:**
- Modify: `detent/stages/lint.py`
- Modify: `detent/stages/typecheck.py`
- Modify: `detent/stages/tests.py`
- Delete: `detent/stages/lint_js.py`, `detent/stages/typecheck_js.py`, `detent/stages/tests_js.py`

- [ ] **Step 1: Rewrite lint.py**

Replace with a clean dispatch pattern:

```python
"""LintStage — dispatches to language-specific lint helpers."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from detent.pipeline.result import VerificationResult
from detent.stages import javascript, python
from detent.stages.base import VerificationStage, _detect_language, _validate_file_path

if TYPE_CHECKING:
    from detent.schema import AgentAction

logger = logging.getLogger(__name__)


class LintStage(VerificationStage):
    """Lints proposed file content. Python->ruff, JS/TS->eslint, Go->go vet, Rust->cargo clippy."""

    name = "lint"

    def supports_language(self, lang: str) -> bool:
        return lang in {"python", "javascript", "typescript", "go", "rust"}

    async def _run(self, action: AgentAction) -> VerificationResult:
        start = time.perf_counter()
        file_path = action.file_path or ""
        content = action.content or ""
        if file_path:
            _validate_file_path(file_path)

        lang = _detect_language(file_path)
        timeout = self._config.timeout if self._config else 30

        if lang == "python":
            findings = await python.run_ruff(file_path, content, self.name, timeout)
            tool = "ruff"
        elif lang in ("javascript", "typescript"):
            findings = await javascript.run_eslint(file_path, content, self.name, timeout)
            tool = "eslint"
        elif lang == "go":
            from detent.stages import go as _go
            findings = await _go.run_vet(file_path, content, self.name, timeout)
            tool = "go vet"
        elif lang == "rust":
            from detent.stages import rust as _rust
            findings = await _rust.run_clippy(file_path, content, self.name, timeout)
            tool = "cargo clippy"
        else:
            findings = []
            tool = "none"

        duration_ms = (time.perf_counter() - start) * 1000
        return VerificationResult(
            stage=self.name,
            passed=not any(f.severity == "error" for f in findings),
            findings=findings,
            duration_ms=duration_ms,
            metadata={"tool": tool, "language": lang},
        )
```

- [ ] **Step 2: Rewrite typecheck.py**

Same dispatch pattern:
- python → `python.run_mypy()`
- javascript/typescript → `javascript.run_tsc()`
- go → `go_helpers.run_build()`
- rust → `rust_helpers.run_check()`
- `supports_language()` returns `lang in {"python", "javascript", "typescript", "go", "rust"}`
- `metadata={"tool": tool, "language": lang}`

- [ ] **Step 3: Rewrite tests.py**

Same dispatch pattern:
- python → `python.run_pytest(file_path, self.name, timeout)` (no content)
- javascript/typescript → `javascript.run_jest(file_path, self.name, timeout, tool_override)`
- go → `go_helpers.run_test(file_path, self.name, timeout)` (no content)
- rust → `rust_helpers.run_test(file_path, self.name, timeout)` (no content)
- `supports_language()` returns `lang in {"python", "javascript", "typescript", "go", "rust"}`

- [ ] **Step 4: Delete superseded files**

```
git rm detent/stages/lint_js.py detent/stages/typecheck_js.py detent/stages/tests_js.py
```

- [ ] **Step 5: Run full unit suite; fix any breakage**

```
uv run pytest tests/unit/ -q 2>&1 | tail -15
```

If `test_tests_stage.py` has `metadata["skipped"]` assertions for the Python no-test-files case, update them to check `result.passed is True` and `result.findings == []`.

- [ ] **Step 6: Lint + format check**

```
uv run ruff check detent/ tests/ && uv run ruff format --check detent/ tests/
```

- [ ] **Step 7: Commit**

```
git add detent/stages/lint.py detent/stages/typecheck.py detent/stages/tests.py
git commit -m "refactor: wire python.py and javascript.py into stages; delete old helpers"
```

---

## Chunk 3: Go Stage

### Task 7: Create go.py with unit tests

**Files:**
- Create: `detent/stages/go.py`
- Create: `tests/unit/test_go_stage.py`

- [ ] **Step 1: Write failing unit tests**

Create `tests/unit/test_go_stage.py` with tests for:

```python
# find_module_root tests
def test_find_module_root_finds_go_mod(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/mymod\n\ngo 1.21\n")
    src_dir = tmp_path / "internal" / "proxy"
    src_dir.mkdir(parents=True)
    assert find_module_root(str(src_dir / "handler.go")) == tmp_path

def test_find_module_root_returns_none_when_missing(tmp_path):
    (tmp_path / "src").mkdir()
    assert find_module_root(str(tmp_path / "src" / "main.go")) is None

def test_find_module_root_finds_go_mod_in_parent(tmp_path):
    (tmp_path / "go.mod").write_text("module ex\n\ngo 1.21\n")
    deep = tmp_path / "a" / "b" / "c"
    deep.mkdir(parents=True)
    assert find_module_root(str(deep / "file.go")) == tmp_path

# run_vet tests
async def test_run_vet_go_not_installed():
    # patch asyncio.create_subprocess_exec to raise FileNotFoundError
    # assert warning finding with "go not found"

async def test_run_vet_no_go_mod(tmp_path):
    # no go.mod in tmp_path
    # assert warning finding with "go.mod"

async def test_run_vet_clean_returns_empty(tmp_path):
    # go.mod present, mock proc returncode=0
    # assert findings == []

async def test_run_vet_returns_warning_findings(tmp_path):
    # go.mod present, mock proc returncode=1, stderr has "main.go:5:2: x declared..."
    # assert len(findings)==1, severity=="warning", file remapped to file_path

# run_build tests
async def test_run_build_compile_error_returns_error_finding(tmp_path):
    # mock returncode=1, stderr has compile error
    # assert severity=="error"

# run_test tests
async def test_run_test_no_go_mod(tmp_path):
    # assert warning finding

async def test_run_test_no_test_files_returns_empty(tmp_path):
    # mock stdout with '[no test files]' output line
    # assert findings == []

async def test_run_test_failed_test_returns_error(tmp_path):
    # mock stdout with go test -json output: Action=output, Action=fail for TestFoo
    # assert error finding with "TestFoo"
```

Use `unittest.mock.patch("asyncio.create_subprocess_exec", ...)` with `MagicMock` + `AsyncMock` for `communicate`.

- [ ] **Step 2: Run to verify they fail**

```
uv run pytest tests/unit/test_go_stage.py -q 2>&1 | tail -5
```

Expected: ImportError or collection error.

- [ ] **Step 3: Implement `detent/stages/go.py`**

```python
"""Go verification helpers: go vet, go build, go test."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from pathlib import Path

from detent.pipeline.result import Finding

logger = logging.getLogger(__name__)

_GO_STDERR_RE = re.compile(r"^(.+):(\d+):(\d+):\s+(.+)$")


def find_module_root(file_path: str) -> Path | None:
    """Walk up from file_path until go.mod found; return that dir or None."""
    current = Path(file_path).resolve().parent
    while True:
        if (current / "go.mod").exists():
            return current
        if current.parent == current:
            return None
        current = current.parent


def _pkg_path(file_path: str, module_root: Path) -> str:
    rel = Path(file_path).parent.resolve().relative_to(module_root)
    return "./" + str(rel) if str(rel) != "." else "."


def _not_found_finding(file_path: str, stage_name: str) -> Finding:
    return Finding(severity="warning", file=file_path, line=None, column=None,
                   message="go not found — install from https://go.dev/dl",
                   code="go/not-installed", stage=stage_name, fix_suggestion=None)


def _no_mod_finding(file_path: str, stage_name: str) -> Finding:
    return Finding(severity="warning", file=file_path, line=None, column=None,
                   message="no go.mod found — is this a Go module?",
                   code="go/no-module", stage=stage_name, fix_suggestion=None)


def _parse_go_stderr(stderr: bytes, file_path: str, stage_name: str, severity: str) -> list[Finding]:
    findings: list[Finding] = []
    for line in stderr.decode("utf-8", errors="replace").splitlines():
        m = _GO_STDERR_RE.match(line.strip())
        if m:
            findings.append(Finding(
                severity=severity,  # type: ignore[arg-type]
                file=file_path,
                line=int(m.group(2)), column=int(m.group(3)),
                message=m.group(4), code=None,
                stage=stage_name, fix_suggestion=None,
            ))
    return findings


async def run_vet(file_path: str, content: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run go vet on the package containing file_path."""
    module_root = find_module_root(file_path)
    if module_root is None:
        return [_no_mod_finding(file_path, stage_name)]
    Path(file_path).write_text(content, encoding="utf-8")
    pkg = _pkg_path(file_path, module_root)
    try:
        proc = await asyncio.create_subprocess_exec(
            "go", "vet", pkg, cwd=str(module_root),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return [_not_found_finding(file_path, stage_name)]
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.communicate()
        return [Finding(severity="warning", file=file_path, line=None, column=None,
                        message=f"go vet timed out after {timeout}s",
                        code="go/timeout", stage=stage_name, fix_suggestion=None)]
    if proc.returncode == 0:
        return []
    if proc.returncode is not None and proc.returncode >= 2:
        return [Finding(severity="warning", file=file_path, line=None, column=None,
                        message=f"go vet internal error: {stderr.decode('utf-8', errors='replace').strip()[:200]}",
                        code="go/vet-error", stage=stage_name, fix_suggestion=None)]
    return _parse_go_stderr(stderr, file_path, stage_name, "warning")


async def run_build(file_path: str, content: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run go build on the package; compile errors -> error findings."""
    module_root = find_module_root(file_path)
    if module_root is None:
        return [_no_mod_finding(file_path, stage_name)]
    Path(file_path).write_text(content, encoding="utf-8")
    pkg = _pkg_path(file_path, module_root)
    try:
        proc = await asyncio.create_subprocess_exec(
            "go", "build", pkg, cwd=str(module_root),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return [_not_found_finding(file_path, stage_name)]
    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.communicate()
        return [Finding(severity="warning", file=file_path, line=None, column=None,
                        message=f"go build timed out after {timeout}s",
                        code="go/timeout", stage=stage_name, fix_suggestion=None)]
    if proc.returncode == 0:
        return []
    if proc.returncode is not None and proc.returncode >= 2:
        return [Finding(severity="warning", file=file_path, line=None, column=None,
                        message=f"go build internal error: {stderr.decode('utf-8', errors='replace').strip()[:200]}",
                        code="go/build-error", stage=stage_name, fix_suggestion=None)]
    return _parse_go_stderr(stderr, file_path, stage_name, "error")


async def run_test(file_path: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run go test -json on the package containing file_path."""
    module_root = find_module_root(file_path)
    if module_root is None:
        return [_no_mod_finding(file_path, stage_name)]
    pkg = _pkg_path(file_path, module_root)
    try:
        proc = await asyncio.create_subprocess_exec(
            "go", "test", "-json", pkg, cwd=str(module_root),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return [_not_found_finding(file_path, stage_name)]
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.communicate()
        return [Finding(severity="warning", file=file_path, line=None, column=None,
                        message=f"go test timed out after {timeout}s",
                        code="go/timeout", stage=stage_name, fix_suggestion=None)]
    if proc.returncode is not None and proc.returncode >= 2:
        return [Finding(severity="warning", file=file_path, line=None, column=None,
                        message=f"go test build error: {stderr.decode('utf-8', errors='replace').strip()[:200]}",
                        code="go/test-build-error", stage=stage_name, fix_suggestion=None)]
    return _parse_go_test_json(stdout, file_path, stage_name)


def _parse_go_test_json(stdout: bytes, file_path: str, stage_name: str) -> list[Finding]:
    output_cache: dict[str, list[str]] = {}
    findings: list[Finding] = []
    for raw_line in stdout.decode("utf-8", errors="replace").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            logger.debug("[%s] go test: malformed JSON: %s", stage_name, raw_line)
            continue
        action = obj.get("Action", "")
        test_name = obj.get("Test", "")
        output = obj.get("Output", "")
        if "[no test files]" in output:
            return []
        if action == "output" and test_name:
            output_cache.setdefault(test_name, []).append(output)
        elif action == "fail" and test_name:
            cached = "".join(output_cache.get(test_name, []))
            findings.append(Finding(
                severity="error", file=file_path, line=None, column=None,
                message=f"Test failed: {test_name} — {cached.strip()[:300]}",
                code="go/test-failed", stage=stage_name, fix_suggestion=None,
            ))
            output_cache.pop(test_name, None)
        elif action in ("pass", "skip") and test_name:
            output_cache.pop(test_name, None)
    return findings
```

- [ ] **Step 4: Run go.py unit tests**

```
uv run pytest tests/unit/test_go_stage.py -v 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 5: Add stage dispatch tests to test_go_stage.py**

Add tests that instantiate `LintStage`, `TypecheckStage`, `TestsStage` and verify:
- `supports_language("go") is True` for all three
- `LintStage().run(make_action(...go file...))` returns `metadata["tool"] == "go vet"` and `metadata["language"] == "go"` (mock subprocess)
- `TypecheckStage().run(...)` returns `metadata["tool"] == "go build"`

- [ ] **Step 6: Run full unit suite**

```
uv run pytest tests/unit/ -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 7: Commit**

```
git add detent/stages/go.py tests/unit/test_go_stage.py
git commit -m "feat: add go.py — Go verification helpers (vet, build, test)"
```

---

## Chunk 4: Rust Stage

### Task 8: Create rust.py with unit tests

**Files:**
- Create: `detent/stages/rust.py`
- Create: `tests/unit/test_rust_stage.py`
- Modify: `pyproject.toml` (add `tomli` for Python <3.11)

- [ ] **Step 1: Add tomli for Python <3.11**

In `pyproject.toml` dependencies add:

```toml
"tomli>=2.0; python_version < '3.11'",
```

Then:
```
uv sync --all-extras --dev
```

- [ ] **Step 2: Write failing unit tests**

Create `tests/unit/test_rust_stage.py` with tests for:

```python
# find_crate_root tests
def test_find_crate_root_finds_cargo_toml(tmp_path):
    # write Cargo.toml with [package] name = "myapp"
    # assert result == (tmp_path, "myapp")

def test_find_crate_root_returns_none_when_missing(tmp_path):
    # no Cargo.toml
    # assert result is None

def test_find_crate_root_workspace_finds_member(tmp_path):
    # workspace Cargo.toml with members = ["crates/mylib"]
    # member Cargo.toml with name = "mylib"
    # file path in crates/mylib/src/
    # assert result == (tmp_path, "mylib")

# run_clippy tests
async def test_run_clippy_cargo_not_installed():
    # FileNotFoundError -> warning "cargo not found"

async def test_run_clippy_no_cargo_toml(tmp_path):
    # no Cargo.toml -> warning "Cargo.toml"

async def test_run_clippy_clean_returns_empty(tmp_path):
    # Cargo.toml present, mock returncode=0 -> []

async def test_run_clippy_returns_warning_findings(tmp_path):
    # mock returncode=1, stdout has compiler-message JSON with level="warning"
    # assert warning finding, line=2, file remapped to file_path

# run_check tests
async def test_run_check_error_finding(tmp_path):
    # compiler-message JSON with level="error"
    # assert error finding

# run_test tests
async def test_run_test_no_cargo_toml(tmp_path):
    # assert warning finding

async def test_run_test_all_pass_returns_empty(tmp_path):
    # stdout: "running 2 tests\ntest it_works ... ok\n...\ntest result: ok."
    # returncode=0 -> []

async def test_run_test_failed_test_returns_error(tmp_path):
    # stdout has "test it_fails ... FAILED"
    # assert error finding with "it_fails"
```

- [ ] **Step 3: Run to verify they fail**

```
uv run pytest tests/unit/test_rust_stage.py -q 2>&1 | tail -5
```

Expected: ImportError or collection error.

- [ ] **Step 4: Implement `detent/stages/rust.py`**

```python
"""Rust verification helpers: cargo clippy, cargo check, cargo test."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
from pathlib import Path

try:
    import tomllib
except ImportError:
    import tomli as tomllib  # type: ignore[no-redef]

from detent.pipeline.result import Finding

logger = logging.getLogger(__name__)


def find_crate_root(file_path: str) -> tuple[Path, str] | None:
    """Walk up to find Cargo.toml; return (root, crate_name) or None.

    Handles workspace Cargo.toml by finding the member containing file_path.
    """
    current = Path(file_path).resolve().parent
    while True:
        cargo_toml = current / "Cargo.toml"
        if cargo_toml.exists():
            try:
                data = tomllib.loads(cargo_toml.read_text(encoding="utf-8"))
            except Exception:
                return None
            if "package" in data:
                return current, data["package"]["name"]
            if "workspace" in data:
                file_resolved = Path(file_path).resolve()
                for pattern in data["workspace"].get("members", []):
                    for member_dir in current.glob(pattern):
                        if not (member_dir / "Cargo.toml").exists():
                            continue
                        try:
                            file_resolved.relative_to(member_dir)
                        except ValueError:
                            continue
                        try:
                            md = tomllib.loads((member_dir / "Cargo.toml").read_text(encoding="utf-8"))
                            return current, md["package"]["name"]
                        except Exception:
                            return None
                return None
        if current.parent == current:
            return None
        current = current.parent


def _not_found_finding(file_path: str, stage_name: str) -> Finding:
    return Finding(severity="warning", file=file_path, line=None, column=None,
                   message="cargo not found — install from https://rustup.rs",
                   code="cargo/not-installed", stage=stage_name, fix_suggestion=None)


def _no_cargo_finding(file_path: str, stage_name: str) -> Finding:
    return Finding(severity="warning", file=file_path, line=None, column=None,
                   message="no Cargo.toml found — is this a Rust crate?",
                   code="cargo/no-manifest", stage=stage_name, fix_suggestion=None)


def _parse_cargo_json(stdout: bytes, file_path: str, stage_name: str) -> list[Finding]:
    """Parse cargo --message-format=json; process only reason=compiler-message."""
    findings: list[Finding] = []
    for raw_line in stdout.decode("utf-8", errors="replace").splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            obj = json.loads(raw_line)
        except json.JSONDecodeError:
            continue
        if obj.get("reason") != "compiler-message":
            continue
        msg = obj.get("message", {})
        level = msg.get("level", "")
        if level in ("note", "help"):
            continue
        severity = "error" if level == "error" else "warning"
        line: int | None = None
        col: int | None = None
        for span in msg.get("spans", []):
            if span.get("is_primary"):
                line = span.get("line_start")
                col = span.get("column_start")
                break
        code_obj = msg.get("code") or {}
        findings.append(Finding(
            severity=severity,  # type: ignore[arg-type]
            file=file_path, line=line, column=col,
            message=msg.get("message", ""),
            code=f"cargo/{code_obj.get('code', 'unknown')}",
            stage=stage_name, fix_suggestion=None,
        ))
    return findings


async def _run_cargo(cmd: list[str], crate_root: Path, timeout: int) -> tuple[bytes, bytes, int | None]:
    proc = await asyncio.create_subprocess_exec(
        *cmd, cwd=str(crate_root),
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        await proc.communicate()
        raise
    return stdout, stderr, proc.returncode


async def run_clippy(file_path: str, content: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run cargo clippy --message-format=json."""
    info = find_crate_root(file_path)
    if info is None:
        return [_no_cargo_finding(file_path, stage_name)]
    crate_root, crate_name = info
    Path(file_path).write_text(content, encoding="utf-8")
    try:
        stdout, stderr, rc = await _run_cargo(
            ["cargo", "clippy", "--message-format=json", "-p", crate_name],
            crate_root, timeout,
        )
    except FileNotFoundError:
        return [_not_found_finding(file_path, stage_name)]
    except TimeoutError:
        return [Finding(severity="warning", file=file_path, line=None, column=None,
                        message=f"cargo clippy timed out after {timeout}s",
                        code="cargo/timeout", stage=stage_name, fix_suggestion=None)]
    if rc == 0:
        return []
    if rc is not None and rc >= 101:
        return [Finding(severity="warning", file=file_path, line=None, column=None,
                        message=f"cargo clippy error: {stderr.decode('utf-8', errors='replace').strip()[:200]}",
                        code="cargo/clippy-error", stage=stage_name, fix_suggestion=None)]
    return _parse_cargo_json(stdout, file_path, stage_name)


async def run_check(file_path: str, content: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run cargo check --message-format=json."""
    info = find_crate_root(file_path)
    if info is None:
        return [_no_cargo_finding(file_path, stage_name)]
    crate_root, crate_name = info
    Path(file_path).write_text(content, encoding="utf-8")
    try:
        stdout, stderr, rc = await _run_cargo(
            ["cargo", "check", "--message-format=json", "-p", crate_name],
            crate_root, timeout,
        )
    except FileNotFoundError:
        return [_not_found_finding(file_path, stage_name)]
    except TimeoutError:
        return [Finding(severity="warning", file=file_path, line=None, column=None,
                        message=f"cargo check timed out after {timeout}s",
                        code="cargo/timeout", stage=stage_name, fix_suggestion=None)]
    if rc == 0:
        return []
    if rc is not None and rc >= 101:
        return [Finding(severity="warning", file=file_path, line=None, column=None,
                        message=f"cargo check error: {stderr.decode('utf-8', errors='replace').strip()[:200]}",
                        code="cargo/check-error", stage=stage_name, fix_suggestion=None)]
    return _parse_cargo_json(stdout, file_path, stage_name)


_FAIL_RE = re.compile(r"^test\s+(\S+)\s+\.\.\.\s+FAILED$")


async def run_test(file_path: str, stage_name: str, timeout: int) -> list[Finding]:
    """Run cargo test -p <crate>."""
    info = find_crate_root(file_path)
    if info is None:
        return [_no_cargo_finding(file_path, stage_name)]
    crate_root, crate_name = info
    try:
        stdout, stderr, rc = await _run_cargo(
            ["cargo", "test", "-p", crate_name], crate_root, timeout,
        )
    except FileNotFoundError:
        return [_not_found_finding(file_path, stage_name)]
    except TimeoutError:
        return [Finding(severity="warning", file=file_path, line=None, column=None,
                        message=f"cargo test timed out after {timeout}s",
                        code="cargo/timeout", stage=stage_name, fix_suggestion=None)]
    if rc == 101:
        return [Finding(severity="warning", file=file_path, line=None, column=None,
                        message=f"cargo test binary compile error: {stderr.decode('utf-8', errors='replace').strip()[:200]}",
                        code="cargo/test-compile-error", stage=stage_name, fix_suggestion=None)]
    if rc == 0:
        return []
    return _parse_cargo_test_output(stdout.decode("utf-8", errors="replace"), file_path, stage_name)


def _parse_cargo_test_output(output: str, file_path: str, stage_name: str) -> list[Finding]:
    findings = []
    for line in output.splitlines():
        if "running 0 tests" in line:
            return []
        m = _FAIL_RE.match(line.strip())
        if m:
            findings.append(Finding(
                severity="error", file=file_path, line=None, column=None,
                message=f"Test failed: {m.group(1)}",
                code="cargo/test-failed", stage=stage_name, fix_suggestion=None,
            ))
    return findings
```

- [ ] **Step 5: Run Rust unit tests**

```
uv run pytest tests/unit/test_rust_stage.py -v 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 6: Add Rust dispatch tests to test_rust_stage.py**

Add:
- `test_lint_stage_supports_rust()` — `LintStage().supports_language("rust") is True`
- `test_typecheck_stage_supports_rust()` — same
- `test_tests_stage_supports_rust()` — same
- `test_lint_stage_dispatches_to_clippy(tmp_path)` — mock subprocess, assert `metadata["tool"] == "cargo clippy"`
- `test_typecheck_stage_dispatches_to_check(tmp_path)` — assert `metadata["tool"] == "cargo check"`

- [ ] **Step 7: Run full unit suite**

```
uv run pytest tests/unit/ -q 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 8: Commit**

```
git add detent/stages/rust.py tests/unit/test_rust_stage.py pyproject.toml uv.lock
git commit -m "feat: add rust.py — Rust verification helpers (clippy, check, test)"
```

---

## Chunk 5: Integration Tests + Final Polish

### Task 9: Go integration tests

**Files:**
- Create: `tests/integration/test_go_integration.py`

- [ ] **Step 1: Create integration test file**

```python
"""Integration tests for Go verification stages (require go installed)."""
import shutil
from pathlib import Path
import pytest
from detent.stages.go import run_build, run_vet
from detent.stages.syntax import SyntaxStage
from tests.conftest import make_action

pytestmark = pytest.mark.skipif(shutil.which("go") is None, reason="go not installed")

@pytest.fixture
def go_module(tmp_path):
    (tmp_path / "go.mod").write_text("module example.com/test\n\ngo 1.21\n")
    return tmp_path

VALID_GO = "package main\n\nfunc main() {}\n"
SYNTAX_ERROR_GO = "package main\n\nfunc main( {\n"
TYPE_ERROR_GO = 'package main\n\nfunc main() {\n\tvar x int = "not an int"\n\t_ = x\n}\n'

# Tests:
# test_syntax_stage_valid_go_passes
# test_syntax_stage_invalid_go_fails — assert findings[0].severity == "error"
# test_run_build_type_error_returns_error_finding — assert any(f.severity=="error")
# test_run_build_valid_go_returns_empty
# test_run_vet_valid_returns_empty
```

- [ ] **Step 2: Run integration tests**

```
uv run pytest tests/integration/test_go_integration.py -v 2>&1 | tail -15
```

Expected: pass (or skip if go not installed).

- [ ] **Step 3: Commit**

```
git add tests/integration/test_go_integration.py
git commit -m "test: add Go integration tests"
```

---

### Task 10: Rust integration tests

**Files:**
- Create: `tests/integration/test_rust_integration.py`

- [ ] **Step 1: Create integration test file**

```python
"""Integration tests for Rust verification stages (require cargo installed)."""
import shutil
from pathlib import Path
import pytest
from detent.stages.rust import run_check, run_clippy
from detent.stages.syntax import SyntaxStage
from tests.conftest import make_action

pytestmark = pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo not installed")

@pytest.fixture
def rust_crate(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "test_crate"\nversion = "0.1.0"\nedition = "2021"\n'
    )
    (tmp_path / "src").mkdir()
    return tmp_path

VALID_RUST = "fn main() {}\n"
SYNTAX_ERROR_RUST = "fn main( {\n"
TYPE_ERROR_RUST = 'fn main() {\n    let x: i32 = "not an int";\n    let _ = x;\n}\n'

# Tests:
# test_syntax_stage_valid_rust_passes
# test_syntax_stage_invalid_rust_fails — assert not result.passed, findings > 0
# test_run_check_type_error_returns_error_finding — assert any(f.severity=="error"), all(f.file==file_path)
# test_run_check_valid_rust_returns_empty
# test_run_clippy_valid_returns_empty
```

- [ ] **Step 2: Run integration tests**

```
uv run pytest tests/integration/test_rust_integration.py -v 2>&1 | tail -15
```

Expected: pass (or skip if cargo not installed).

- [ ] **Step 3: Commit**

```
git add tests/integration/test_rust_integration.py
git commit -m "test: add Rust integration tests"
```

---

### Task 11: Final polish + PR

- [ ] **Step 1: Full lint check**

```
uv run ruff check detent/ tests/
```

Fix any issues.

- [ ] **Step 2: Format check**

```
uv run ruff format --check detent/ tests/
```

Auto-fix if needed: `uv run ruff format detent/ tests/`

- [ ] **Step 3: Full unit test suite**

```
uv run pytest tests/unit/ -q 2>&1 | tail -10
```

Expected: all pass. Record count for PR description.

- [ ] **Step 4: Commit any fixes**

```
git add -u
git commit -m "chore: final lint and format fixes"
```

- [ ] **Step 5: Push and open PR**

```
git push -u origin feature/go-rust-stages
gh pr create --title "feat: add Go and Rust verification stages" --base develop \
  --body "$(cat <<'EOF'
## Summary

- **Go support**: \`go.py\` — \`go vet\` (lint), \`go build\` (typecheck), \`go test -json\` (tests); write-then-check pattern; \`find_module_root()\` walks up to \`go.mod\`
- **Rust support**: \`rust.py\` — \`cargo clippy\` (lint), \`cargo check\` (typecheck), \`cargo test\` (tests); workspace-aware \`find_crate_root()\`; \`tomllib\`/\`tomli\` for TOML parsing
- **Syntax**: \`SyntaxStage\` uses language-name-keyed \`_GRAMMAR_MAP\` with \`tree-sitter-go\` and \`tree-sitter-rust\` grammars
- **Refactor**: \`python.py\` and \`javascript.py\` consolidate per-tool logic; \`lint_js.py\`, \`typecheck_js.py\`, \`tests_js.py\` deleted
- **Stages**: \`lint.py\`, \`typecheck.py\`, \`tests.py\` rewritten with clean language dispatch

## Test plan

- [ ] \`uv run pytest tests/unit/ -q\` → all pass
- [ ] \`uv run pytest tests/integration/test_go_integration.py -v\` → pass (requires go)
- [ ] \`uv run pytest tests/integration/test_rust_integration.py -v\` → pass (requires cargo)
- [ ] \`uv run ruff check detent/ tests/\` → clean
- [ ] \`uv run ruff format --check detent/ tests/\` → clean

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

---

*End of plan.*
