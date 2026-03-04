# Phase 3 — Verification Stages

> **Status:** ✅ Done
> **Depends on:** Phase 1
> **Branch:** `feature/verification-stages`

## Goal

Build the four individual verification stages. Each is independent, receives `AgentAction`, and returns `VerificationResult`. Python-focused in v0.1.

## Files

### New

| File                                 | Description                            |
| ------------------------------------ | -------------------------------------- |
| `detent/pipeline/result.py`          | `Finding`, `VerificationResult` models |
| `detent/stages/base.py`              | `VerificationStage` ABC                |
| `detent/stages/syntax.py`            | `SyntaxStage` — tree-sitter            |
| `detent/stages/lint.py`              | `LintStage` — Ruff                     |
| `detent/stages/typecheck.py`         | `TypecheckStage` — mypy                |
| `detent/stages/tests.py`             | `TestsStage` — pytest                  |
| `tests/unit/test_syntax_stage.py`    | Syntax stage tests                     |
| `tests/unit/test_lint_stage.py`      | Lint stage tests                       |
| `tests/unit/test_typecheck_stage.py` | Typecheck stage tests                  |
| `tests/unit/test_tests_stage.py`     | Test execution stage tests             |

## Design

### Finding

```python
class Finding(BaseModel):
    severity: Literal["error", "warning", "info"]
    file: str
    line: int | None
    column: int | None
    message: str
    code: str | None
    stage: str
    fix_suggestion: str | None
```

### VerificationResult

```python
class VerificationResult(BaseModel):
    stage: str
    passed: bool
    findings: list[Finding]
    duration_ms: float
    metadata: dict[str, Any]
```

### VerificationStage (ABC)

```python
class VerificationStage(ABC):
    name: str
    async run(action: AgentAction) -> VerificationResult
    supports_language(lang: str) -> bool
```

- Built-in exception wrapping: if `run()` throws, return a safe `VerificationResult` with error Finding — **never crash the pipeline**

### Stages

| Stage            | Tool        | Method                                                                |
| ---------------- | ----------- | --------------------------------------------------------------------- |
| `SyntaxStage`    | tree-sitter | Parse proposed content, detect syntax errors with line/column         |
| `LintStage`      | Ruff        | Write to temp file, `ruff check --output-format json`, parse results  |
| `TypecheckStage` | mypy        | Write to temp file, `mypy --output json`, parse results               |
| `TestsStage`     | pytest      | `pytest -k <pattern> --tb=short -q`, discover tests for modified file |

All subprocess calls use `asyncio.create_subprocess_exec`.

## Tests

| Stage         | Test Cases                                                                                              |
| ------------- | ------------------------------------------------------------------------------------------------------- |
| **Syntax**    | Valid Python → pass; invalid syntax → fail with line/col; unsupported lang → skip; empty/binary content |
| **Lint**      | Clean code → pass; lint violations → findings; Ruff JSON parsing against real output                    |
| **Typecheck** | Type-correct → pass; type errors → findings with locations; mypy JSON parsing                           |
| **Tests**     | Passing tests → pass; failing tests → fail with test names                                              |
