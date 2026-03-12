# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.2] - 2026-03-12

### Fixed

- **HTTP proxy timeout** — Replaced `ClientTimeout(total=5s)` with `ClientTimeout(connect=10s, total=None)` so long-running LLM API calls (streaming responses that take 20-60+ seconds) no longer time out and return 502. The parameter is renamed from `timeout_s` to `connect_timeout_s` to clarify its scope.

## [0.1.1] - 2026-03-12

### Fixed

- **HTTP proxy SSL certificate verification** — `DetentProxy` now creates an `aiohttp.TCPConnector` backed by a `certifi`-based SSL context, resolving `CERTIFICATE_VERIFY_FAILED` errors on macOS where Python's default ssl module does not load the system keychain. A custom `ssl.SSLContext` can be passed via the new `ssl_context` constructor parameter.

### Changed

- Added `certifi>=2024.0` as an explicit direct dependency (was previously only a transitive dependency via `aiohttp`).

## [0.1.0] - 2026-03-08

### Added

- **Complete v0.1 Proof of Concept** — Full verification runtime with all core features
- **CLI Interface** — Four commands for verification workflow:
  - `detent init` — Interactive setup wizard
  - `detent run <file>` — Verify single file and report findings
  - `detent status` — Display session checkpoint state
  - `detent rollback <ref>` — Restore file from checkpoint
- **Python SDK** — 27 public APIs for programmatic use:
  - `VerificationPipeline` — Main orchestrator
  - `CheckpointEngine` — Atomic SAVEPOINT/rollback
  - `AgentAction`, `VerificationResult`, `Finding` — Core data models
  - `VerificationStage` — Base class for custom stages
  - Agent adapters and configuration classes
- **Checkpoint Engine** — Atomic file backup and restoration:
  - In-memory tracking of checkpoints
  - Shadow git repository for rollback
  - Named checkpoint references (e.g., `chk_before_write_001`)
- **Verification Pipeline** — Composable stage orchestration:
  - Sequential execution (default)
  - Parallel execution with configurable worker count
  - Fail-fast mode (stop at first error)
  - Language-aware stage filtering (Python-focused in v0.1)
- **Verification Stages** (4 included):
  - **SyntaxStage** — tree-sitter syntax validation
  - **LintStage** — Ruff linting integration
  - **TypecheckStage** — mypy type checking integration
  - **TestsStage** — pytest test runner integration
- **Feedback Synthesis Engine** — LLM-optimized output:
  - Structured JSON feedback format
  - Tool-specific output parsing (mypy, ruff, pytest)
  - Human-readable messages with fix suggestions
  - Severity classification (error/warning)
- **Agent Adapters** (2 included):
  - **Claude Code Adapter** — PreToolUse/PostToolUse hooks
  - **LangGraph Adapter** — VerificationNode for LangGraph workflows
- **HTTP Reverse Proxy** — Conversation-layer interception (Point 1):
  - aiohttp-based proxy on configurable port
  - Tool call extraction from LLM responses
  - Retry logic with exponential backoff
  - Session state persistence
- **IPC Control Channel** — Tool execution layer coordination (Point 2):
  - Unix domain socket communication
  - NDJSON message protocol
  - Async/await throughout
- **Configuration System** — YAML-based settings:
  - `DetentConfig` for global settings
  - `PipelineConfig` for verification pipeline
  - `StageConfig` for individual stages
  - `ProxyConfig` for HTTP proxy settings
  - Policy profiles: strict/standard/permissive
- **Test Suite** — 211+ tests covering:
  - Schema and configuration (15 tests)
  - Checkpoint engine (25 tests)
  - Verification stages (90 tests)
  - Verification pipeline (50 tests)
  - Feedback synthesis (20 tests)
  - HTTP proxy and IPC (20 tests)
  - Agent adapters (40 tests)
  - CLI and session management (40+ tests)

### Known Limitations

- **Python-focused** — Only Python verification stages; JavaScript support planned for v1.0
- **Limited agent support** — Claude Code (production) and LangGraph (tested); 5 more agents planned for v1.0
- **Linux/macOS only** — Windows support planned for v1.0
- **No security scanning** — Planned for v1.0 (Semgrep, Bandit)
- **Basic IPC** — Unix domain sockets only; no network communication
- **No web UI** — CLI and SDK only in v0.1

## [Unreleased]

### Planned for v1.0 (Q3 2026)

- TypeScript/JavaScript verification stages (ESLint, TypeScript compiler, Jest)
- Complete agent adapter coverage (Cursor, Aider, LiteLLM, OpenAPI, Gemini, Perplexity)
- Security scanning integration (Semgrep, Bandit)
- GitHub Actions integration and workflow templates
- Windows support
- Performance optimizations and benchmarking
- Plugin system for custom stages and adapters

### Planned for v2.0 (Q1 2027)

- Detent Cloud (managed SaaS)
- Multi-agent orchestration
- VS Code extension
- Advanced analytics and reporting
- Enterprise features (RBAC, audit logging)
