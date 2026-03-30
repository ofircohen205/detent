# Detent Roadmap

This document outlines the planned features and timeline for Detent.

## v0.1 — Proof of Concept ✅ (Complete)

**Released:** March 8, 2026

See the plan documents in `docs/plans/` for complete details.

**Highlights:**

- Dual-point interception (HTTP proxy + agent adapters)
- Checkpoint engine with atomic rollback
- Verification pipeline with 4 stages
- Feedback synthesis engine
- CLI with session management
- Python SDK with 27 public APIs
- 211+ tests with >80% coverage
- Claude Code and LangGraph adapters

## v1.0 — Production Ready ✅ COMPLETE

**Released:** 2026-03-16

### Language Support Expansion

- [x] TypeScript/JavaScript verification stages
  - ESLint integration
  - TypeScript compiler (tsc)
  - Jest test runner
- [x] Go verification stages
  - go vet linting
  - go build type check
  - `go test` runner
- [x] Rust verification stages
  - clippy linting
  - cargo check type check
  - cargo test

### Agent Adapter Coverage

4 agents fully supported:

- [x] Claude Code — HTTP proxy (Point 1) + PreToolUse hook (Point 2)
- [x] Codex CLI — HTTP proxy (Point 1) + pre-exec hook (Point 2)
- [x] Gemini CLI — BeforeTool hook (Point 2)
- [x] LangGraph — VerificationNode (Point 2)

### Security Features

- [x] Semgrep integration for security scanning
- [x] Bandit for Python security
- [x] SAST/DAST pipeline integration
  - Secret scanning: detect-secrets on every file write (hardcoded secrets, API keys, tokens)
  - Dependency scanning: pip-audit on requirements*.txt files (CVE lookup via OSV database)

### Platform Support

- [x] Docker improvements
  - Multi-stage Dockerfile + docker-compose.yml

### CI/CD Integration

- [x] GitHub Actions integration
  - ci.yml, pre-publish.yml, publish.yml, security.yml, stale.yml

### Performance & Reliability

- [x] Benchmark suite
  - pytest-benchmark suite measuring pipeline overhead and checkpoint rollback latency
  - Benchmark CI workflow with threshold enforcement and step summary reporting
- [x] Distributed tracing (OpenTelemetry)
  - Tracer, metrics, exporter, schemas in detent/observability/
- [x] Circuit breaker for stages
  - detent/circuit_breaker.py

### Test Coverage

- [x] 427+ tests with >80% coverage

### Documentation

- [x] Core documentation suite
  - `README.md` — quick start, feature overview, agent comparison table, SDK examples
  - `AGENTS.md` — comprehensive architecture guide: dual-point interception, normalized action schema, all four agent adapters, verification pipeline stages, checkpoint SAVEPOINT semantics, feedback synthesis engine, Python SDK reference, extension guides
  - `DEVELOPMENT.md` — local development guide: project structure, Make targets, Docker, environment variables, test matrix
  - `INSTALLATION.md` — installation guide for pip, uv, and source; per-agent hook setup; policy profiles
  - `CONTRIBUTING.md` — contributor workflow: branching, TDD, code review, CI requirements
  - `SUPPORT.md` — support channels and issue escalation
  - `AUTHORS.md` — project authors and contributors
  - `SECURITY.md` — vulnerability disclosure policy and contact

- [x] Architecture deep dives (covered in `AGENTS.md`)
  - Dual-point interception model (HTTP proxy vs hook adapters)
  - Checkpoint engine: SAVEPOINT per tool call, in-memory + shadow git, atomic rollback
  - Verification pipeline: stage composition, parallel execution, fail-fast semantics
  - Feedback synthesis: raw tool output → structured LLM-optimized JSON
  - Agent adapter matrix: normalization to `AgentAction`, hook scope, file-write guard

- [x] Integration guides (covered in `README.md` and `AGENTS.md`)
  - Claude Code: HTTP proxy + PreToolUse hook
  - Codex CLI: HTTP proxy + pre-exec hook (`.codex/hooks.json`)
  - Gemini CLI: BeforeTool hook
  - LangGraph: VerificationNode drop-in
  - Policy profiles: strict, standard, permissive

- [x] API reference documentation
  - Auto-generated from docstrings via pdoc
  - `make docs` builds to `docs/api/`; `make serve-docs` for local preview
  - Published to GitHub Pages on push to `main` via `.github/workflows/docs.yml`
  - Covers all 33 public exports in `detent/__init__.py`

- [x] Video tutorials (written tutorial guides)
  - `docs/tutorials/01-getting-started.md` — install, init, first interception, SDK usage
  - `docs/tutorials/02-claude-code.md` — dual-point setup, hook scope, troubleshooting
  - `docs/tutorials/03-codex.md` — hooks.json setup, proxy, payload formats
  - `docs/tutorials/04-gemini.md` — BeforeTool hook, tool name mapping, limitations
  - `docs/tutorials/05-langgraph.md` — VerificationNode wiring, custom config, routing

## v1.1 — Hook Scope & Adapter Correctness ✅ COMPLETE

**Released:** 2026-03-28

### Hook Scope Fix

- [x] Claude Code PreToolUse hook matcher scoped to file-write tools only (`Write|Edit|NotebookEdit`) — was firing on every tool call
- [x] Adapter-level FILE_WRITE guard as defense-in-depth across all hook adapters (Claude Code, Codex, Gemini)
- [x] Gemini adapter: isolated native tool names (`write_file`, `edit`) to `GeminiAdapter._ACTION_TYPE_MAP`; normalized missing tool name to return `None`
- [x] Port validation added to `configure_claude_code_hook()` and `configure_codex_hook()` (raises `ValueError` for out-of-range ports)
- [x] Symlink escape protection in hook config writers (rejects `.claude/` or `.codex/` that resolve outside project root)

### Codex Hook Config Fix

- [x] Codex hook config moved to `.codex/hooks.json` (was incorrectly using `.codex/instructions.md`)
- [x] Migration logic: stale Detent hook entries with wrong matcher are upgraded in-place on next `detent init`

## v2.0 — Enterprise Platform

### Cloud Platform

- [ ] Detent Cloud (managed SaaS)
  - Multi-tenant architecture
  - API for managing verifications
  - Estimated effort: 8 weeks
- [ ] Webhook integrations
  - GitHub, GitLab, Bitbucket
  - Estimated effort: 2 weeks

### Advanced Features

- [ ] Multi-agent orchestration
  - Coordinate multiple agents
  - Agent voting/consensus
  - Estimated effort: 3 weeks
- [ ] Custom verification plugins
  - Plugin marketplace
  - Community contributions
  - Estimated effort: 2 weeks
- [ ] LLM-assisted feedback synthesis
  - Use Claude/GPT for better suggestions
  - Estimated effort: 2 weeks

### Developer Tools

- [ ] VS Code extension
  - Real-time verification in editor
  - Checkpoint management UI
  - Estimated effort: 4 weeks
- [ ] IDE plugins (JetBrains, Vim)
  - Estimated effort: 2 weeks each

### Enterprise Features

- [ ] Role-based access control (RBAC)
  - Team management
  - Permission scoping
  - Estimated effort: 2 weeks
- [ ] Audit logging
  - Compliance tracking
  - Estimated effort: 1.5 weeks
- [ ] Advanced analytics
  - Agent performance metrics
  - Vulnerability trends
  - Estimated effort: 2 weeks

## Contributing to the Roadmap

Have an idea for Detent? We'd love to hear it!

### Feature Requests

1. Check if it's [already planned](https://github.com/ofircohen205/detent/issues)
2. Open a [GitHub issue](https://github.com/ofircohen205/detent/issues/new) with tag `[FEATURE]`
3. Describe:
   - What problem it solves
   - Why it matters
   - How it fits Detent's vision

### Voting & Discussion

- 👍 React to issues you care about
- Comment with use cases and feedback
- Join [GitHub Discussions](https://github.com/ofircohen205/detent/discussions)

### Implementation

Want to implement a feature yourself? See [CONTRIBUTING.md](./CONTRIBUTING.md)!

---

Last updated: 2026-03-30
