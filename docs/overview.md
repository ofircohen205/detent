# Detent v0.1 Project Overview

**Status:** ✅ **v0.1 Proof of Concept — Complete**

**Last Updated:** 2026-03-08

---

## Executive Summary

Detent v0.1 is a complete proof-of-concept verification runtime that intercepts AI agent file writes at the tool call level, runs them through a configurable verification pipeline, and atomically rolls back if verification fails.

**Key Milestones:**
- ✅ All 8 phases complete
- ✅ 211+ unit and integration tests passing
- ✅ Full CLI with session management
- ✅ Python SDK with 28 public APIs
- ✅ Dual-point interception (HTTP proxy + agent adapters)
- ✅ Atomic checkpoint engine with rollback
- ✅ Composable verification pipeline
- ✅ LLM-optimized feedback synthesis

---

## Phase Completion Status

### Phase 0: Documentation Cleanup
**Status:** ✅ Complete
**Focus:** Project scaffolding, documentation foundation
**Deliverables:** Architecture docs, project structure, AGENTS.md, CLAUDE.md

### Phase 1: Schema & Configuration
**Status:** ✅ Complete — PR #1 merged
**Focus:** Core data models and configuration system
**Deliverables:**
- `detent/schema.py` — AgentAction, ActionType, RiskLevel
- `detent/config.py` — DetentConfig, PipelineConfig, StageConfig, ProxyConfig
- Configuration validation with Pydantic
- `detent.yaml` example configuration

### Phase 2: Checkpoint Engine
**Status:** ✅ Complete — PR #2 merged
**Focus:** Atomic SAVEPOINT and rollback mechanism
**Deliverables:**
- `detent/checkpoint/engine.py` — CheckpointEngine class
- `detent/checkpoint/savepoint.py` — SAVEPOINT/rollback logic
- In-memory checkpoint tracking
- Shadow git repository for rollback
- Atomic file restoration

### Phase 3: Verification Stages
**Status:** ✅ Complete — PR #3 merged
**Focus:** Pluggable verification stages
**Deliverables:**
- `detent/stages/base.py` — VerificationStage base class
- `detent/stages/syntax.py` — tree-sitter syntax validation
- `detent/stages/lint.py` — Ruff linting integration
- `detent/stages/typecheck.py` — mypy type checking integration
- `detent/stages/tests.py` — pytest test runner integration
- STAGE_REGISTRY for plugin discovery
- 90+ unit tests for all stages

### Phase 4: Verification Pipeline
**Status:** ✅ Complete — PR #4 merged
**Focus:** Composable pipeline orchestration
**Deliverables:**
- `detent/pipeline/pipeline.py` — VerificationPipeline
- `detent/pipeline/result.py` — VerificationResult, Finding
- Sequential, parallel, and fail-fast execution modes
- Language-aware stage filtering
- Per-stage metadata aggregation
- 50+ integration tests

### Phase 5: Feedback Synthesis
**Status:** ✅ Complete — PR #5 merged
**Focus:** LLM-optimized feedback generation
**Deliverables:**
- `detent/feedback/synthesizer.py` — FeedbackSynthesizer
- StructuredFeedback and EnrichedFinding models
- Tool-specific output parsing (mypy, ruff, pytest JSON)
- Human-readable message generation with fix suggestions
- Comprehensive test coverage

### Phase 6: HTTP Proxy & IPC
**Status:** ✅ Complete — PR #6 merged
**Focus:** Conversation-layer interception
**Deliverables:**
- `detent/proxy/http_proxy.py` — DetentProxy (aiohttp-based)
- `detent/ipc/channel.py` — IPCControlChannel (Unix domain sockets)
- Session state persistence
- Retry logic with exponential backoff
- Message-based control flow (NDJSON protocol)

### Phase 7: Agent Adapters
**Status:** ✅ Complete — PR #7 merged
**Focus:** Agent-specific interception
**Deliverables:**
- `detent/adapters/base.py` — AgentAdapter base class
- `detent/adapters/claude_code.py` — Claude Code PreToolUse/PostToolUse hooks
- `detent/adapters/langgraph.py` — LangGraph VerificationNode
- Normalized action translation from agent-specific tool calls
- 40+ adapter tests

### Phase 8: CLI & SDK
**Status:** ✅ Complete — PR #8 merged
**Focus:** User interface and public API
**Deliverables:**
- `detent/cli.py` — Click-based CLI with 4 commands:
  - `detent init` — Interactive setup wizard
  - `detent run <file>` — Verify and report on single file
  - `detent status` — Show session state with checkpoints
  - `detent rollback <ref>` — Restore from named checkpoint
- SessionManager for CLI session persistence
- Rich terminal output with formatting
- `detent/__init__.py` — 28 public API exports
- Updated `pyproject.toml` with entry point
- 40+ CLI and integration tests

---

## Architecture Overview

### Two-Point Interception

```
Point 1 (Conversation Layer):
  AI Agent ──[LLM API traffic]──► HTTP Reverse Proxy (DetentProxy)
  • See what agent plans to do (intent interception)
  • Extract tool calls from LLM responses

Point 2 (Tool Execution Layer):
  Agent ──[tool call: Write]──► Agent Adapter ──► Filesystem
  • Enforce what agent is allowed to do (action interception)
  • Create checkpoint, run verification, rollback if needed
```

### Component Hierarchy

```
CLI Layer (detent/cli.py)
  ├─ SessionManager (session state persistence)
  └─ Commands: init, run, status, rollback

Runtime Layer
  ├─ HTTP Proxy (DetentProxy) — Point 1 interception
  ├─ Agent Adapters (Claude Code, LangGraph) — Point 2 interception
  └─ Session Manager (proxy/session.py) — verification coordination

Verification Pipeline
  ├─ VerificationPipeline — orchestrator
  ├─ Verification Stages:
  │  ├─ SyntaxStage
  │  ├─ LintStage
  │  ├─ TypecheckStage
  │  └─ TestsStage
  └─ Feedback Synthesizer — LLM-optimized output

Checkpoint Engine
  ├─ CheckpointEngine — SAVEPOINT creator
  ├─ Shadow Git Repository — atomic rollback
  └─ In-memory Tracking — fast checkpoint lookup
```

---

## Test Summary

**Total Tests:** 211+

| Category | Count | Status |
|----------|-------|--------|
| Schema & Config | 15 | ✅ |
| Checkpoint Engine | 25 | ✅ |
| Verification Stages | 90 | ✅ |
| Verification Pipeline | 50 | ✅ |
| Feedback Synthesis | 20 | ✅ |
| HTTP Proxy & IPC | 20 | ✅ |
| Agent Adapters | 40 | ✅ |
| CLI & Sessions | 40 | ✅ |

**Test Coverage:** >80% of production code

---

## Key Features Implemented

✅ **Dual-point interception** — Both conversation and action layers
✅ **Atomic rollback** — SAVEPOINT semantics for file operations
✅ **Composable pipeline** — Sequential, parallel, fail-fast modes
✅ **Language awareness** — Stage filtering based on file type
✅ **Structured feedback** — LLM-optimized JSON output
✅ **Session management** — Persistent checkpoint tracking
✅ **Interactive CLI** — Setup wizard, status display, manual rollback
✅ **Python SDK** — 28 public APIs for programmatic use
✅ **Agent adapters** — Claude Code and LangGraph out-of-the-box
✅ **Comprehensive tests** — Unit, integration, and end-to-end coverage

---

## Known Limitations & Future Work

### v0.1 Scope Limitations

- **Python-focused:** Only Python verification stages (ruff, mypy, pytest)
- **Single agent focus:** Claude Code primary, LangGraph basic support
- **No web UI:** CLI and SDK only
- **Linux/macOS only:** Windows support in v1.0
- **Basic IPC:** Unix domain sockets (NDJSON protocol)

### v1.0 Roadmap

- [ ] TypeScript/JavaScript verification stages (ESLint, tsc, Jest)
- [ ] All 7 agent adapters (Cursor, Aider, LiteLLM, etc.)
- [ ] Security scanning (Semgrep, Bandit)
- [ ] Plugin system for custom stages
- [ ] GitHub Actions integration
- [ ] OpenTelemetry observability
- [ ] Windows support

### v2.0 Roadmap

- [ ] Detent Cloud (SaaS)
- [ ] Multi-agent orchestration
- [ ] VS Code extension
- [ ] LLM-assisted feedback synthesis

---

## Quick Start

```bash
# Install
pip install detent

# Initialize in a project
detent init

# Run verification on a file
detent run src/main.py

# Check session state
detent status

# Rollback if needed
detent rollback chk_before_write_000
```

---

## File Structure

```
detent/
├── detent/
│   ├── __init__.py              # 28 public API exports
│   ├── schema.py                # AgentAction, ActionType, RiskLevel
│   ├── config.py                # DetentConfig, StageConfig, etc.
│   ├── cli.py                   # CLI commands (init, run, status, rollback)
│   ├── proxy/
│   │   ├── http_proxy.py        # HTTP reverse proxy
│   │   ├── session.py           # Session manager (runtime coordination)
│   │   └── types.py             # IPC message types
│   ├── adapters/
│   │   ├── base.py              # AgentAdapter base
│   │   ├── claude_code.py       # Claude Code hooks
│   │   └── langgraph.py         # LangGraph VerificationNode
│   ├── checkpoint/
│   │   ├── engine.py            # CheckpointEngine
│   │   └── savepoint.py         # SAVEPOINT/rollback logic
│   ├── pipeline/
│   │   ├── pipeline.py          # VerificationPipeline orchestrator
│   │   └── result.py            # VerificationResult, Finding
│   ├── stages/
│   │   ├── base.py              # VerificationStage base
│   │   ├── syntax.py            # tree-sitter syntax validation
│   │   ├── lint.py              # Ruff linting
│   │   ├── typecheck.py         # mypy type checking
│   │   └── tests.py             # pytest integration
│   ├── feedback/
│   │   └── synthesizer.py       # FeedbackSynthesizer
│   └── ipc/
│       └── channel.py           # IPC control channel
├── tests/
│   ├── unit/                    # 150+ unit tests
│   └── integration/             # 60+ integration tests
├── docs/
│   ├── plans/                   # Phase implementation plans
│   ├── PRD.docx                 # Product Requirements
│   ├── SRS.docx                 # System Requirements
│   ├── ADD.docx                 # Architecture & Design
│   └── overview.md              # This file
├── detent.yaml                  # Example configuration
├── pyproject.toml               # Dependencies & metadata
├── CLAUDE.md                    # Claude Code guidance
├── AGENTS.md                    # Agent documentation
├── GEMINI.md                    # Gemini guidance
├── Makefile                     # Development commands
├── Dockerfile                   # Container image
└── README.md                    # Project README
```

---

## How to Use

### As a CLI Tool

```bash
# Initialize Detent in your project
cd my-project
detent init

# Verify a file before committing
detent run src/main.py

# Check what checkpoints exist
detent status

# Rollback to a previous version if needed
detent rollback chk_before_write_001
```

### As a Python SDK

```python
from detent import (
    VerificationPipeline,
    CheckpointEngine,
    AgentAction,
    ActionType,
    DetentConfig,
)

# Load configuration
config = DetentConfig.from_yaml("detent.yaml")

# Create pipeline
pipeline = VerificationPipeline.from_config(config)

# Create action
action = AgentAction(
    action_type=ActionType.FILE_WRITE,
    tool_name="Write",
    file_path="src/main.py",
    tool_input={"content": "..."},
)

# Run verification
result = await pipeline.run(action)

if result.passed:
    print("✅ Verification passed")
else:
    print(f"❌ {len(result.findings)} issues found")
```

### With Claude Code (Agent Adapter)

Set the environment variable to route Claude Code through Detent:

```bash
export ANTHROPIC_BASE_URL=http://localhost:7070
```

Start the Detent proxy:

```bash
detent run --proxy
```

Claude Code will now intercept tool calls through Detent's verification pipeline.

---

## Development Commands

```bash
# Install all dependencies (including dev/extras)
make install

# Run all tests
make test

# Fast unit tests only
make test-unit

# Tests with coverage report
make test-cov

# Lint and format check
make check

# Clean build artifacts
make clean

# Build Docker image
make docker-build

# Run Docker container
make docker-run

# Full docker-compose stack
make compose-up
```

---

## Documentation

- **[AGENTS.md](../AGENTS.md)** — Verification stages, adapters, checkpoint engine details
- **[CLAUDE.md](../CLAUDE.md)** — Claude Code integration and guidance
- **[docs/PRD.docx](./PRD.docx)** — Product Requirements Document
- **[docs/SRS.docx](./SRS.docx)** — System Requirements Specification
- **[docs/ADD.docx](./ADD.docx)** — Architecture & Design Document
- **[docs/plans/](./plans/)** — Phase-by-phase implementation plans

---

## Contributors

Built as part of the Detent v0.1 Proof of Concept (8 phases, 8 weeks)

---

**v0.1 Status:** ✅ Complete and production-ready for proof-of-concept
**Date Completed:** March 8, 2026
