# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [1.2.0] - 2026-03-29

### Added

- **Secret scanning sub-stage** — `detent/stages/security/_secrets.py` integrates `detect-secrets` into the `SecurityStage`; runs concurrently with Semgrep and Bandit on every file write; returns one error Finding per detected secret with a fix suggestion to use an environment variable or secrets manager
- **Dependency vulnerability scanning sub-stage** — `detent/stages/security/_dep_scan.py` integrates `pip-audit` into the `SecurityStage`; scans `requirements*.txt` files for known CVEs via the OSV database before they are written to disk; returns one error Finding per vulnerable package with upgrade guidance
- **`detect-secrets` added to security optional extras** — `pip install detent[security]` now installs `detect-secrets>=1.5,<2` alongside Semgrep and Bandit
- **`detent.yaml` `secrets` and `dep_scan` config sections** — both new sub-scanners are enabled by default; can be individually disabled via `secrets.enabled: false` / `dep_scan.enabled: false`
- **Context-aware extension guard** — hook adapters (Claude Code, Codex, Gemini) and the LangGraph adapter now use `is_verifiable_file()` from `detent.config.languages`; code files (`.py`, `.ts`, `.go`, `.rs`, etc.) and dependency manifests (`requirements*.txt`, `pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`) pass through; all other file types are skipped without verification

## [1.1.0] - 2026-03-26

### Added

- **Comprehensive adapter logging** — all agent adapters emit structured logs at every stage: intercept start/end, errors, verification result handling, and performance timing; shared `_log_*` helpers added to `AgentAdapter` and `HTTPProxyAdapter` base classes
- **`ClaudeCodeHookAdapter`** — Point 2 enforcement adapter for Claude Code `PreToolUse` hooks (`/hooks/claude-code`); returns `permissionDecision` allow/deny with structured feedback
- **`CodexHookAdapter`** — Point 2 enforcement adapter for Codex CLI pre-exec hooks (`/hooks/codex`); handles flat and nested OpenAI-style payloads; returns `approved`/`decision`
- **Auto-wired hook configuration** — `detent init` writes the `PreToolUse` hook into `.claude/settings.json` (Claude Code) and `.codex/instructions.md` (Codex) automatically; idempotent, merges with existing settings
- **`configure_claude_code_hook()` and `configure_codex_hook()`** — programmatic hook setup utilities in `detent.cli.utils`
- **Hooks vs proxy documentation** — new "Using Hooks vs Proxy" section in `AGENTS.md` with per-agent setup instructions; README Quick Start updated with hook setup examples per agent

### Changed

- **Terminal-first adapter scope** — removed Cursor, LiteLLM, and OpenAPI adapters (not terminal-based coding assistants); supported agents are now Claude Code, Codex, and Gemini (hook enforcement) plus LangGraph (VerificationNode)
- **Hook adapters registered at proxy startup** — `detent proxy` registers Point 2 hook adapters on the aiohttp app before `start()` so enforcement is active immediately
- **Agent choices in `detent init`** updated to `[claude-code, codex, gemini, langgraph]`

## [1.0.6] - 2026-03-25

### Fixed

- **Rich runtime dependency removed** — `rich` was incorrectly listed as a runtime dependency; moved to `dev` extras so end-users are not required to install it

## [1.0.5] - 2026-03-25

### Fixed

- **Codex Responses API parsing** — support OpenAI Responses API `output[]` tool items (`function_call`, `custom_tool_call`, `mcp_call`) in addition to chat-completions `tool_calls`
- **Cursor provider-aware Point 1 parsing** — select the HTTP response parser from `proxy.upstream_url` or the resolved upstream host instead of hard-wiring Point 1 parsing to `agent=cursor`
- **Gemini CLI hook compatibility** — parse Gemini CLI `BeforeTool` payloads using `tool_name` and `tool_input`, while retaining compatibility with older `functionCall` payloads

## [1.0.4] - 2026-03-24

### Fixed

- **HTTP proxy adapter wiring** — wire `detent proxy` to a live `SessionManager`, `VerificationPipeline`, IPC channel, and agent-specific HTTP adapter so Point 1 now observes tool intents and runs speculative verification instead of acting as a pure pass-through
- **Claude Code response parsing** — parse Anthropic `content[].type == "tool_use"` responses in the HTTP adapter while preserving existing PreToolUse hook parsing
- **Hook exception safety** — fail open with HTTP 200 on unexpected pipeline/result-handler exceptions so hook-based agent sessions are not broken by Detent internal errors

## [1.0.3] - 2026-03-23

### Fixed

- **Proxy `ZlibError`** — strip `Content-Encoding` and `Content-Length` from upstream responses before forwarding; aiohttp auto-decompresses gzip bodies on `resp.read()`, so forwarding `Content-Encoding: gzip` caused Claude Code to attempt a second decompression, resulting in `ZlibError`

## [1.0.2] - 2026-03-17

### Fixed

- **Proxy `InvalidHTTPResponse`** — strip hop-by-hop headers (`Transfer-Encoding`, `Connection`, etc.) from upstream responses before forwarding; the proxy fully buffers the response body so chunked encoding is already decoded, but the stale headers caused Claude Code's HTTP client to raise `InvalidHTTPResponse`

### Changed

- **Logging** — replace stdlib `logging` with `structlog 24+` across all 46 source files; new `detent/observability/logging.py` exposes `configure_logging(level, json=False)` with console renderer by default and JSON lines for production; stdlib integration captures aiohttp and other third-party logs

## [1.0.1] - 2026-03-16

### Fixed

- **PyPI publish**: re-release to resolve initial publish issue

## [1.0.0] - 2026-03-16

### Added

- **Security Stage** — Semgrep + Bandit static analysis, concurrent execution, deduplication
- **Go & Rust verification stages** — `go vet`/`go build`/`go test` and `cargo check`/`clippy`/`cargo test`
- **TypeScript/JavaScript stages** — ESLint lint and `tsc` typecheck support
- **OpenAI adapter** — Interception for Cursor, Codex, and other OpenAI-compatible agents
- **OpenTelemetry observability** — Distributed tracing and metrics with circuit breakers
- **Docker support** — `Dockerfile`, `docker-compose.yml`, and `Makefile` targets
- **CI/CD workflows** — `ci.yml` (lint + typecheck + tests), `security.yml` (bandit, pip-audit, detect-secrets), `pre-publish.yml` and `publish.yml` (PyPI release gate)
- **324 tests** — Full unit and integration coverage across all stages and adapters

### Fixed

- **Semgrep exit code** — v1.x returns exit code 0 even when findings exist; now always parses JSON output regardless of exit code
- **Cargo check robustness** — Parses stdout JSON first on any non-zero exit code before falling back to generic warning
- **Observability ImportError** — `setup_telemetry` now wraps missing SDK errors with a human-readable message
- **mypy unused-ignore** — Added override for `opentelemetry.exporter.otlp.proto.grpc` to handle environments where the package may or may not be installed

### Changed

- **Project structure refactored** — Stages split into language-specific helpers; adapters reorganised into `http` and `hook` packages
- Version bumped from `0.1.2` → `1.0.0`

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
- **Linux/macOS only** — Windows is not supported
- **No security scanning** — Planned for v1.0 (Semgrep, Bandit)
- **Basic IPC** — Unix domain sockets only; no network communication
- **No web UI** — CLI and SDK only in v0.1

## [Unreleased]

### Planned for v1.0 (Q3 2026)

- TypeScript/JavaScript verification stages (ESLint, TypeScript compiler, Jest)
- Security scanning integration (Semgrep, Bandit)
- GitHub Actions integration and workflow templates
- Performance optimizations and benchmarking
- Plugin system for custom stages and adapters

### Planned for v2.0 (Q1 2027)

- Detent Cloud (managed SaaS)
- Multi-agent orchestration
- VS Code extension
- Advanced analytics and reporting
- Enterprise features (RBAC, audit logging)
