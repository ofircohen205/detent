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
- [ ] Cursor IDE adapter — planned
- [ ] Aider (CLI agent) adapter — planned
- [ ] LiteLLM adapter (multi-model) — planned
- [ ] OpenAPI / custom agents — planned

### Security Features

- [x] Semgrep integration for security scanning
- [x] Bandit for Python security
- [ ] SAST/DAST pipeline integration
  - Estimated effort: 2 weeks

### Platform Support

- [ ] Windows support
  - Shadow git on Windows
  - Windows-compatible paths
  - v2.0 goal
- [x] Docker improvements
  - Multi-stage Dockerfile + docker-compose.yml

### CI/CD Integration

- [x] GitHub Actions integration
  - ci.yml, pre-publish.yml, publish.yml, security.yml, stale.yml
- [ ] GitLab CI templates
  - Estimated effort: 1 week
- [ ] Jenkins plugin
  - Estimated effort: 2 weeks

### Performance & Reliability

- [ ] Benchmark suite
  - Measure proxy overhead
  - Stage execution times
  - Estimated effort: 1 week
- [x] Distributed tracing (OpenTelemetry)
  - Tracer, metrics, exporter, schemas in detent/observability/
- [x] Circuit breaker for stages
  - detent/circuit_breaker.py

### Test Coverage

- [x] 427+ tests with >80% coverage

### Documentation

- [ ] API reference documentation
  - Auto-generated from docstrings
  - Estimated effort: 1 week
- [ ] Video tutorials
  - Getting started
  - Integration guides
  - Estimated effort: 2 weeks
- [ ] Architecture deep dives
  - Estimated effort: 1 week

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

Last updated: 2026-03-28
