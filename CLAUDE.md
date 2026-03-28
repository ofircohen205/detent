# CLAUDE.md

This file provides guidance to Claude Code when working with code in this repository.

> **Important:** When making significant corrections to approaches, code patterns, or architectural decisions, update this file (CLAUDE.md) to prevent repeating the same mistakes in future sessions.

## Repository Information

**Git Repository:** https://github.com/ofircohen205/detent

**Project:** Detent — a verification runtime that sits between AI coding agents and the filesystem, intercepting every file write, running it through a configurable verification pipeline, and atomically rolling back if the code fails.

## Project Overview

Detent is **not** a code review product, code generation tool, or CI plugin. It is a protocol-level proxy that intercepts AI agent tool calls in real time — before they hit the filesystem.

**Core value proposition:**

- **Intercept** file writes at the tool call level (before execution)
- **Verify** proposed content through a composable pipeline (syntax → lint → typecheck → tests → security)
- **Rollback** atomically via checkpoint engine (SAVEPOINT semantics applied to file operations)
- **Synthesize** structured feedback optimized for LLM self-repair (not raw linter output)

**Current Status:**

- ✅ v0.1 (Proof of Concept) — Complete. Full package with CLI, SDK exports, session management, verification pipeline, checkpoint engine, and 324+ tests.
- ✅ v1.0 (Production Ready) — Complete (released 2026-03-16)
- ✅ v1.1 (Hook Scope Fix) — Complete (released 2026-03-28). Hook matcher scoped to file-write tools only; Codex hook config corrected; 427+ tests.
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

# Run verification on a file manually
detent run src/main.py

# Check current session checkpoint state
detent status

# Manually rollback to a named checkpoint
detent rollback [checkpoint-name]

# Development commands
uv run pytest tests/ -v
uv run pytest tests/unit/ -v          # fast, no external deps
uv run pytest tests/integration/ -v  # full pipeline
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
  • Set ANTHROPIC_BASE_URL (Claude Code) or OPENAI_BASE_URL (Cursor/Codex)
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
│   ├── http/          ← claude_code.py, codex.py, providers.py
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
    agent: str           # "claude-code" | "cursor" | "aider" | ...
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
   - Remove dead code (unused imports, commented-out blocks) when making changes
   - DRY: if the same logic appears 2+ times, refactor into a shared function

2. **Temporary Files:**
   - All temporary test files, debugging scripts go in `tmp/` (gitignored)
   - Never commit `tmp/`

3. **Documentation:**
   - Update [CLAUDE.md](./CLAUDE.md), [GEMINI.md](./GEMINI.md), [AGENTS.md](./AGENTS.md) for architectural changes
   - Add docstrings to all new classes and functions
   - Update inline comments for complex logic

4. **Logging:**
   - Every significant operation MUST include detailed logging
   - Use structured logging with appropriate levels (DEBUG, INFO, WARNING, ERROR)
   - Required in stages: log start, tool command, completion, and findings count

### Git Workflow

1. **Commit Discipline:**
   - Make frequent, small commits rather than large, monolithic ones
   - Use conventional commit messages: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`
   - **Do NOT add `Co-Authored-By:` footers** — all commits are by the user

2. **Protected Branches:**
   - NEVER commit directly to `main` branch
   - All work should be done in feature branches
   - Use pull requests for code review before merging

3. **Plan Execution Branches:**
   - **ALWAYS create a new git worktree + branch before executing any implementation plan**
   - Branch naming: `feature/<plan-topic>` (e.g., `feature/syntax-stage`)
   - Worktrees live in `.worktrees/<branch-name>/` (gitignored)
   - Create with: `git worktree add .worktrees/<branch> -b feature/<branch>`
   - Never execute plan tasks directly on `main` or the current working branch

4. **Code Review & CI:**
   - All code changes are subject to automated code review via GitHub Actions (`.github/workflows/ci.yml`)
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
   - Verify your parsing of tool output (mypy JSON, Ruff JSON, Semgrep JSON) against real tool output
   - Test with known-bad and known-good code samples, not just mocks
   - A stage that incorrectly blocks valid code is as bad as one that misses real bugs

2. **Never crash the pipeline on stage failure:**
   - If a stage throws an unexpected exception, it should return a safe error finding — not propagate the exception
   - The agent session must not be broken by a Detent internal error

3. **Rollback must be atomic:**
   - Always create the SAVEPOINT **before** the write, never after
   - Test rollback under concurrent writes and partial failures

4. **Feedback synthesis quality is the primary investment:**
   - Raw linter output injected into the agent context degrades self-repair (see OpenHands research)
   - Every finding must have: severity, file, line, human-readable message, fix_suggestion (where deterministic)

5. **Performance constraints:**
   - Proxy overhead: <5ms per tool call
   - Rollback latency: <500ms
   - Profile any new stage; async I/O for all subprocess calls

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
from detent.stages.security import SecurityStage

# Checkpoint
from detent.checkpoint.engine import CheckpointEngine

# Adapters
from detent.adapters.base import AgentAdapter
from detent.adapters.http.claude_code import ClaudeCodeAdapter
from detent.adapters.langgraph import VerificationNode

# Observability
from detent.observability import setup_telemetry

# Config
from detent.config import DetentConfig
```

### Adding a New Verification Stage

See [AGENTS.md → Adding New Verification Stages](./AGENTS.md#adding-new-verification-stages) for the full guide.

Quick steps:

1. Create `detent/stages/my_stage.py` implementing `VerificationStage`
2. Add to `detent/stages/__init__.py`
3. Register in `STAGE_REGISTRY`
4. Enable in `detent.yaml`
5. Write unit tests in `tests/unit/test_my_stage.py`

### Adding a New Agent Adapter

See [AGENTS.md → Adding New Agent Adapters](./AGENTS.md#adding-new-agent-adapters) for the full guide.

Quick steps:

1. Create `detent/adapters/my_agent.py` implementing `AgentAdapter`
2. Register in `detent/adapters/__init__.py` ADAPTERS dict
3. Write tests verifying normalization to `AgentAction`

### Code Style

- **Python:** Follow PEP 8, use type hints, async/await for all I/O
- **Testing:** >80% coverage, test real tool output parsing (not just mocks)
- **Commits:** Use conventional commits (feat:, fix:, docs:, etc.)

## Environment Variables

```bash
ANTHROPIC_BASE_URL=http://localhost:7070   # Route Claude Code traffic through Detent
OPENAI_BASE_URL=http://localhost:7070      # Route Cursor/Codex traffic through Detent
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
  - Full unit tests for pipeline and checkpoint engine (324+ tests) ✅

- ✅ **v1.0 (Production Ready) — Complete (released 2026-03-16):**
  - HTTP adapters (Claude Code, Codex) + hook adapters (Claude Code, Codex, Gemini) ✅
  - LangGraph VerificationNode ✅
  - Multi-language stages: Python, JavaScript/TypeScript, Go, Rust ✅
  - Security scanning (Semgrep + Bandit) ✅
  - OpenTelemetry tracing + metrics; circuit breakers ✅
  - Docker + docker-compose ✅

- ✅ **v1.1 (Hook Scope Fix) — Complete (released 2026-03-28):**
  - PreToolUse hook matcher scoped to `Write|Edit|NotebookEdit` ✅
  - Codex hook config corrected to `.codex/hooks.json` ✅
  - Adapter-level FILE_WRITE guard; Gemini tool name isolation ✅
  - 427+ tests ✅

- ⏳ **v2.0 (Enterprise Platform) — Planned:**
  - Detent Cloud (managed SaaS); multi-agent orchestration; VS Code extension

See [docs/PRD.docx](./docs/PRD.docx) for full requirements.

## Testing

```bash
# Run all tests
uv run pytest tests/ -v

# Unit tests only (fast, no external tool deps)
uv run pytest tests/unit/ -v

# Integration tests (requires tools: ruff, mypy, etc. installed)
uv run pytest tests/integration/ -v

# Single test
uv run pytest tests/unit/test_syntax_stage.py::test_name -v

# With coverage
uv run pytest tests/ --cov=detent --cov-report=term-missing
```

**Always use `uv run pytest`**, never bare `pytest` or `python -m pytest`.

**Test philosophy:**

- Unit tests: test each stage/adapter in isolation with mock `AgentAction` objects and real (captured) tool output fixtures
- Integration tests: test the full pipeline with real tools (ruff, mypy) on known-good and known-bad Python/TS files
- Rollback tests: verify atomicity under partial failure scenarios

## Non-Goals

Do NOT implement these — they are explicitly out of scope:

- ❌ Code review (PR comments, GitHub/GitLab integration)
- ❌ Code generation or completion
- ❌ Token-level constrained decoding (Detent operates at tool call level, not inside LLM sampling)
- ❌ Proprietary verification logic (Detent wraps open-source tools; it does not compete with them)
- ❌ Web UI (v0.1 and v1.0 are CLI + SDK only)
- ❌ Windows support (v0.1 — Linux and macOS only)
- ❌ Built-in LLM (feedback synthesis uses structured templates in v0.1; LLM-assisted is P1)

## External Resources

- [Claude Code hooks](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [LangGraph documentation](https://langchain-ai.github.io/langgraph/)
- [tree-sitter](https://tree-sitter.github.io/tree-sitter/)
- [Ruff](https://docs.astral.sh/ruff/)
- [mypy](https://mypy.readthedocs.io/)
- [Semgrep](https://semgrep.dev/docs/)
- [OpenTelemetry GenAI conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)

## Key Documentation

- [CLAUDE.md](./CLAUDE.md) — This file (Claude Code–specific guidance)
- [GEMINI.md](./GEMINI.md) — Gemini-specific agent guidance
- [AGENTS.md](./AGENTS.md) — Verification stages, adapters, checkpoint engine, SDK
- [docs/PRD.docx](./docs/PRD.docx) — Product Requirements Document
- [docs/SRS.docx](./docs/SRS.docx) — Software Requirements Specification
- [docs/ADD.docx](./docs/ADD.docx) — Architecture & Design Document

## Using the Detent CLI

### Installation

```bash
pip install detent
```

Or from source:

```bash
git clone https://github.com/ofircohen205/detent
cd detent
uv sync
uv run detent init
```

### Quick Start

```bash
# 1. Initialize detent in your project
detent init

# 2. Run verification on a file
detent run src/main.py

# 3. Check session state
detent status

# 4. Rollback a checkpoint if needed
detent rollback chk_before_write_000
```

### Policy Profiles

- **strict** — All stages enabled, any finding blocks the write
- **standard** — P0 stages enabled, warnings do not block (default)
- **permissive** — Syntax only, all other stages as warnings

### SDK Usage

```python
from detent import DetentConfig, VerificationPipeline, AgentAction

config = DetentConfig.load("detent.yaml")
pipeline = VerificationPipeline.from_config(config)

# ... create AgentAction ...
result = await pipeline.run(action)
```

---

**Last Updated:** 2026-03-16
**Version:** 1.0.0
