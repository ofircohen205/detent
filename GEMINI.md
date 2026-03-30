# GEMINI.md

This file provides guidance to Gemini when working with code in this repository.

> **Important:** When making significant corrections to approaches, code patterns, or architectural decisions, update this file (GEMINI.md) to prevent repeating the same mistakes in future sessions.

## Repository Information

**Git Repository:** https://github.com/ofircohen205/detent

**Project:** Detent — a verification runtime that intercepts AI coding agent file writes in real time, runs them through a configurable verification pipeline, and rolls back atomically if the code fails.

## Project Overview

Detent is **not** a code review product, code generation tool, or CI plugin. It is a protocol-level proxy that intercepts AI agent tool calls — before they hit the filesystem.

**Core value proposition:**

- **Intercept** file writes at the tool call level (before execution)
- **Verify** proposed content through a composable pipeline (syntax → lint → typecheck → tests → security)
- **Rollback** atomically via checkpoint engine (SAVEPOINT semantics applied to file operations)
- **Synthesize** structured feedback optimized for LLM self-repair (not raw linter output)

**Current Status:**

- ✅ v0.1 (Proof of Concept) — Complete. v1.0.0 is complete and production-ready.
- ✅ v1.0 (Production Ready) — Complete (released 2026-03-16)
- ⏳ v2.0 (Enterprise Platform) — Planned

**Key Documentation:**

- [AGENTS.md](./AGENTS.md) — Verification stages, agent adapters, checkpoint engine, SDK
- [docs/PRD.docx](./docs/PRD.docx) — Full product requirements document

## Quick Start

### Using Make (recommended)

```bash
make install        # install all dependencies (uv sync --all-extras --dev)
make check          # lint + format check + typecheck
make test           # run full test suite
make test-unit      # fast unit tests only
make test-cov       # tests with coverage report
make clean          # remove all build/cache artifacts
```

### Manual commands

```bash
# Install (once published)
pip install detent

# Development
uv sync

# Initialize in a Claude Code project
detent init

# Development commands
uv run python -m detent.cli run src/main.py   # verify a file
uv run pytest tests/ -v                        # run all tests
uv run pytest tests/unit/ -v                   # unit tests only (fast)
uv run pytest tests/integration/ -v            # integration tests
```

### Docker

```bash
make docker-build      # build the Docker image
make docker-run        # run the proxy on port 7070 (foreground)
make compose-up        # full local stack via docker compose
make compose-down      # stop the stack

# Or run the tools sidecar too:
docker compose --profile tools up
```

## Architecture

### Two Interception Points

```
Point 1 (Conversation Layer):
  AI Agent ──[LLM API traffic]──► HTTP Reverse Proxy (Detent)
  • Set ANTHROPIC_BASE_URL (Claude Code) or OPENAI_BASE_URL (Codex)
  • Sees what the agent plans to do (intent interception)

Point 2 (Tool Execution Layer):
  Agent ──[tool call: Write]──► Agent Adapter (Detent) ──► Filesystem
  • PreToolUse hooks (Claude Code), MCP proxy, LiteLLM callbacks, etc.
  • Enforces what the agent is allowed to do (action interception)
```

### Key Components

| Component                 | Responsibility                                                       |
| ------------------------- | -------------------------------------------------------------------- |
| **HTTP Proxy**            | Intercepts LLM API traffic; extracts tool calls from responses       |
| **Agent Adapters**        | Agent-specific interception (PreToolUse hooks, MCP proxy, etc.)      |
| **Checkpoint Engine**     | SAVEPOINT per tool call; in-memory + shadow git; atomic rollback     |
| **Verification Pipeline** | Composable stages: syntax → lint → typecheck → tests → security      |
| **Feedback Synthesis**    | Converts raw tool output into structured LLM-optimized JSON feedback |
| **CLI**                   | `detent init`, `detent run`, `detent status`, `detent rollback`      |
| **Python SDK**            | `DetentProxy`, `VerificationPipeline`, `VerificationStage`           |

### Project Structure (v1.0.0)

```
detent/
├── __init__.py
├── schema.py
├── circuit_breaker.py
├── adapters/
│   ├── base.py
│   ├── langgraph.py
│   ├── http/          ← claude_code.py, codex.py
│   └── hook/          ← claude_code.py, codex.py, gemini.py
├── checkpoint/        ← engine.py, savepoint.py, schemas.py
├── cli/               ← app.py, init.py, run.py, status.py, rollback.py, proxy.py
├── config/            ← __init__.py, languages.py
├── feedback/          ← synthesizer.py, schemas.py
├── ipc/               ← channel.py, schemas.py
├── observability/     ← tracer.py, metrics.py, exporter.py, schemas.py
├── pipeline/          ← pipeline.py, result.py
├── proxy/             ← http_proxy.py, session.py, types.py
└── stages/
    ├── base.py
    ├── _subprocess.py
    ├── syntax/        ← base.py
    ├── languages/     ← _go.py, _rust.py
    ├── lint/          ← base.py, _ruff.py, _eslint.py, _clippy.py, _go_vet.py
    ├── typecheck/     ← base.py, _mypy.py, _tsc.py, _cargo_check.py, _go_build.py
    ├── tests/         ← base.py, _pytest.py, _jest.py, _cargo_test.py, _go_test.py
    └── security/      ← base.py (Semgrep + Bandit)
```

### Normalized Action Schema

All intercepted events from any agent are normalized to `AgentAction` before the pipeline runs:

```python
class AgentAction:
    action_type: Literal["file_write", "shell_exec", "file_read", "web_fetch", "mcp_tool"]
    agent: str           # "claude-code" | "codex" | "gemini" | "langgraph"
    tool_name: str       # "Write" | "Bash" | "Edit" | ...
    tool_input: dict     # raw tool input (file_path, content, etc.)
    tool_call_id: str
    session_id: str
    checkpoint_ref: str  # "chk_before_write_004"
    risk_level: Literal["low", "medium", "high"]
```

## Core Principles

These apply to every change, no matter how small:

- **Simplicity First:** Make every change as simple as possible. Impact the minimal amount of code necessary.
- **No Laziness:** Find root causes. No temporary fixes. Hold yourself to senior developer standards.
- **Minimal Impact:** Changes should only touch what's necessary. Avoid accidentally introducing bugs in adjacent code.
- **Plan Before You Build:** Enter plan mode for any non-trivial task — 3+ steps, architectural decisions, or anything touching multiple files.
- **Verification Before Done:** Never mark a task complete without proving it works — run tests, check logs, demonstrate correctness.

## Code Quality Standards

### General Coding Principles

1. **Keep Code Clean:**
   - Write clear, maintainable code following established patterns
   - Remove "orphaned" code when making changes (unused imports, dead functions, commented-out blocks)
   - Extract reused code into separate functions or files (DRY principle)
   - If the same code appears 2+ times, refactor it into a shared function

2. **Temporary Files:**
   - All temporary test files, debugging scripts, and experimental code MUST go in the `tmp/` directory
   - The `tmp/` directory is gitignored and should never be committed
   - Clean up temporary files after they're no longer needed

3. **Documentation:**
   - Update relevant documentation files when making architectural changes:
     - [GEMINI.md](./GEMINI.md) — Gemini-specific guidance and corrections (this file)
     - [CLAUDE.md](./CLAUDE.md) — Claude-specific guidance
     - [AGENTS.md](./AGENTS.md) — Verification stages, adapters, and pipeline architecture
   - Add docstrings to all new functions and classes
   - Update inline comments for complex logic

4. **Logging:**
   - Every significant operation MUST include detailed logging
   - Use structured logging with appropriate levels (DEBUG, INFO, WARNING, ERROR)
   - Required log points in each verification stage: stage start, tool command, completion, findings count
   - Include context in logs: file_path, stage name, operation, timing

### Git Workflow

1. **Commit Discipline:**
   - Make frequent, small commits rather than large, monolithic ones
   - Each commit should represent a logical unit of work
   - Use conventional commit messages: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
   - **Warning:** It's easy to get carried away and make dozens of changes without committing
   - If "everything breaks," small commits make it much easier to identify and revert the problematic change

2. **Protected Branches:**
   - NEVER commit directly to `main` branch
   - All work should be done in feature branches
   - Use pull requests for code review before merging

3. **Plan Execution Branches:**
   - **ALWAYS create a new git worktree + branch before executing any implementation plan**
   - Branch naming: `feature/<plan-topic>` (e.g., `feature/syntax-stage`)
   - Worktrees live in `.worktrees/<branch-name>/` (already gitignored)
   - Create with: `git worktree add .worktrees/<branch> -b feature/<branch>`
   - Never execute plan tasks directly on `main` or the current working branch

4. **Code Review & CI:**
   - All code changes are subject to automated review via GitHub Actions (`.github/workflows/ci.yml`)
   - CI runs Ruff lint + format check, mypy, and the full test suite on Python 3.12 and 3.13
   - **IMPORTANT:** Before creating a pull request, verify CI will pass locally:
     - Run `uv run ruff check detent/ tests/` (linting)
     - Run `uv run mypy detent/` (type checking)
     - Run `uv run pytest tests/ -q` (all tests)
     - Fix any failures before pushing or creating the PR
   - Address CI failures before merging

### Project-Specific Guidelines

> **Critical for a verification runtime:**

1. **Correctness of verification output:**
   - Verify your parsing of tool output (mypy JSON, Ruff JSON, Semgrep JSON) against real tool output formats
   - Test with known-bad and known-good code samples, not just mocks
   - A stage that incorrectly blocks valid code is as harmful as one that misses real bugs

2. **Never crash the pipeline on stage failure:**
   - If a stage throws an unexpected exception, return a safe error finding — **do not propagate the exception**
   - An agent session must not be terminated by a Detent internal error

3. **Rollback must be atomic:**
   - Always create the SAVEPOINT **before** the write, never after
   - Test rollback under concurrent writes and partial-failure scenarios

4. **Feedback synthesis quality is the primary investment:**
   - Raw linter output injected into the agent context degrades self-repair (per OpenHands/SWE-bench research)
   - Every finding must include: severity, file, line, human-readable message, and fix_suggestion where deterministic

5. **Performance constraints (non-negotiable):**
   - Proxy overhead: <5ms per tool call
   - Rollback latency: <500ms
   - Profile any new stage; use async I/O for all subprocess calls

6. **Follow Instructions Precisely:**
   - Instructions in GEMINI.md, CLAUDE.md, and AGENTS.md are authoritative
   - If you notice yourself deviating from documented patterns, flag it and ask
   - When in doubt, ask the user rather than making assumptions

## Best Practices

### Import Patterns

```python
# Core schema
from detent.schema import AgentAction

# Pipeline
from detent.pipeline.pipeline import VerificationPipeline
from detent.pipeline.result import VerificationResult, Finding

# Stages
from detent.stages.base import VerificationStage
from detent.stages.syntax import SyntaxStage
from detent.stages.lint import LintStage
from detent.stages.typecheck import TypecheckStage
from detent.stages.tests import TestsStage
from detent.stages.security import SecurityStage

# Checkpoint
from detent.checkpoint.engine import CheckpointEngine

# Adapters
from detent.adapters.base import AgentAdapter
from detent.adapters.http.claude_code import ClaudeCodeAdapter
from detent.adapters.langgraph import VerificationNode

# Observability
from detent.observability import setup_telemetry

# Top-level SDK
from detent import DetentProxy

# Config
from detent.config import DetentConfig
```

### Code Style

- **Python:** Follow PEP 8, use type hints, async/await for all I/O
- **Testing:** Aim for >80% coverage; test real tool output parsing, not just mocks
- **Commits:** Use conventional commits (feat:, fix:, docs:, etc.)

### Working with Verification Stages

- Each stage is independent and can be tested in isolation
- Stages receive `AgentAction` objects — they never touch raw agent-specific payloads
- All stage `run()` methods are async
- Stages should handle tool failures gracefully and return `VerificationResult` — never raise to the pipeline
- See [AGENTS.md](./AGENTS.md) for how to add new stages

### Working with Agent Adapters

- Adapters convert agent-specific raw events to `AgentAction` — that is their only job
- All feedback injection is adapter-specific (e.g., Claude Code uses `additionalContext` in `PreToolUse` exit)
- Test adapters by providing real (captured) agent event fixtures, not fictional ones
- See [AGENTS.md](./AGENTS.md) for how to add new adapters

### Checkpoint Engine

- `CheckpointEngine.savepoint(ref)` must be called **before** any file write
- `CheckpointEngine.rollback(ref)` restores file content to the state at that savepoint
- Shadow git commits provide durable (cross-process) backup; in-memory snapshots provide speed

## Environment Variables

```bash
ANTHROPIC_BASE_URL=http://localhost:7070   # Route Claude Code traffic through Detent
OPENAI_BASE_URL=http://localhost:7070      # Route Codex traffic through Detent
DETENT_CONFIG=./detent.yaml               # Path to config file
DETENT_LOG_LEVEL=INFO                     # DEBUG | INFO | WARNING | ERROR
```

## Implementation Phases

- ✅ **v0.1 (Proof of Concept) — Complete:**
  - Dual-point proxy for Claude Code + LangGraph VerificationNode ✅
  - Checkpoint engine (in-memory + shadow git), atomic rollback ✅
  - Verification pipeline: syntax, lint, typecheck, targeted tests ✅
  - Feedback synthesis engine (structured JSON) ✅
  - `detent.yaml`, `detent init` CLI, Python SDK ✅
  - Full unit tests for pipeline and checkpoint engine ✅

- ✅ **v1.0 (Production Ready) — Complete (released 2026-03-16):**
  - HTTP adapters (Claude Code, Codex) + hook adapters (Claude Code, Codex, Gemini) ✅
  - Multi-language stages: Python, JavaScript/TypeScript, Go, Rust ✅
  - Security scanning (Semgrep + Bandit) ✅
  - OpenTelemetry tracing + metrics; circuit breakers ✅
  - Docker + docker-compose ✅

- ⏳ **v2.0 (Enterprise Platform) — Planned:**
  - Detent Cloud (managed SaaS, SSO, RBAC, audit dashboard); multi-agent orchestration; VS Code extension

See [docs/PRD.docx](./docs/PRD.docx) for full requirements.

## Testing

```bash
# Run all tests
uv run pytest tests/ -v

# Unit tests only (fast, no external tool deps)
uv run pytest tests/unit/ -v

# Integration tests (requires ruff, mypy, etc. installed)
uv run pytest tests/integration/ -v

# Specific domain
uv run pytest tests/unit/test_syntax_stage.py -v
uv run pytest tests/unit/test_checkpoint_engine.py -v

# Single test
uv run pytest tests/unit/test_syntax_stage.py::test_name -v

# With coverage
uv run pytest tests/ --cov=detent --cov-report=term-missing
```

**Always use `uv run pytest`**, never bare `pytest` or `python -m pytest`.

**Test philosophy:**

- Unit tests: test each stage/adapter in isolation with mock `AgentAction` objects; include real captured tool output fixtures
- Integration tests: test the full pipeline with real tools (ruff, mypy) on known-good and known-bad files
- Rollback tests: verify atomicity under partial failure scenarios

## Non-Goals

Do NOT implement these — they are explicitly out of scope for v0.1 and v1.0:

- ❌ Code review (PR comments, GitHub/GitLab integration)
- ❌ Code generation or completion
- ❌ Token-level constrained decoding (operates at tool call level, not inside LLM sampling)
- ❌ Proprietary verification logic (Detent wraps open-source tools — Ruff, mypy, Semgrep)
- ❌ Web UI (CLI + SDK only in v0.1 and v1.0; VS Code extension is v2.0)
- ❌ Windows support (Linux and macOS only)
- ❌ Built-in LLM (feedback synthesis uses structured templates in v0.1; LLM-assisted is P1)

## Key Documentation Files

- [GEMINI.md](./GEMINI.md) — This file (Gemini-specific guidance)
- [CLAUDE.md](./CLAUDE.md) — Claude Code–specific guidance
- [AGENTS.md](./AGENTS.md) — Verification stages, adapters, checkpoint engine, SDK
- [docs/PRD.docx](./docs/PRD.docx) — Product Requirements Document
- [docs/SRS.docx](./docs/SRS.docx) — Software Requirements Specification
- [docs/ADD.docx](./docs/ADD.docx) — Architecture & Design Document

## External Resources

- [Claude Code hooks](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [LangGraph documentation](https://langchain-ai.github.io/langgraph/)
- [tree-sitter](https://tree-sitter.github.io/tree-sitter/)
- [Ruff](https://docs.astral.sh/ruff/)
- [mypy](https://mypy.readthedocs.io/)
- [Semgrep](https://semgrep.dev/docs/)
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)

---

**Last Updated:** 2026-03-16
**Version:** 1.0.0
