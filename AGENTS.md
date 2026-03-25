# AGENTS.md

This document provides a comprehensive guide to the Detent system architecture: its verification pipeline stages, agent adapters, checkpoint engine, and extension points.

> **Important:** When adding new verification stages, agent adapters, or modifying core pipeline behavior, update this file to document the changes and prevent knowledge loss between sessions.

## Table of Contents

1. [Overview](#overview)
2. [Architecture: Two Interception Points](#architecture-two-interception-points)
3. [Agent Adapter Matrix](#agent-adapter-matrix)
4. [Checkpoint Engine & Rollback](#checkpoint-engine--rollback)
5. [Verification Pipeline](#verification-pipeline)
6. [Feedback Synthesis Engine](#feedback-synthesis-engine)
7. [Normalized Action Schema](#normalized-action-schema)
8. [Python SDK](#python-sdk)
9. [Adding New Verification Stages](#adding-new-verification-stages)
10. [Adding New Agent Adapters](#adding-new-agent-adapters)
11. [Testing Stages & Adapters](#testing-stages--adapters)
12. [Development Standards](#development-standards)

---

## Overview

Detent is a **verification runtime** — not a tool wrapper, not a hook script, not a CI plugin. It sits between an AI coding agent and the filesystem, intercepting every write before it executes, running it through a configurable verification pipeline, and atomically rolling back if the code fails.

**Key principles:**

- **Dual-point interception:** Detent intercepts at both the conversation layer (LLM traffic) and the tool execution layer (individual tool calls)
- **Agent-agnostic:** adapter-based design; different hooks per agent, unified normalized schema internally
- **Transactional rollback:** checkpoint engine with SAVEPOINT semantics; rollback is atomic and partial (only the failing call, not the whole session)
- **Feedback quality is the primary investment:** raw linter output is not returned to the agent; it is synthesized into structured, LLM-optimized feedback for self-repair

### Architecture Diagram

```
AI Agent (Claude Code / Cursor / Aider / etc.)
       |
       | (LLM API traffic)
       ↓
┌─────────────────────────────────────┐
│  Point 1: HTTP Reverse Proxy        │  ← Conversation layer (intent interception)
│  (ANTHROPIC_BASE_URL / OPENAI_BASE_URL override)             │
└─────────────────────────────────────┘
       |
       | (tool calls extracted from LLM response)
       ↓
┌─────────────────────────────────────┐
│  Point 2: Agent Adapter             │  ← Tool execution layer (action interception)
│  (PreToolUse hooks / MCP proxy /    │
│   LiteLLM callback / event stream)  │
└─────────────────────────────────────┘
       |
       | (intercepted action → normalized AgentAction)
       ↓
┌─────────────────────────────────────┐
│  Checkpoint Engine                  │  SAVEPOINT created before every write
│  (in-memory + shadow git)           │
└─────────────────────────────────────┘
       |
       ↓
┌─────────────────────────────────────┐
│  Verification Pipeline              │
│                                     │
│  [syntax] → [lint] → [typecheck]    │
│          → [tests] → [security]     │
│          → [custom stages...]       │
└─────────────────────────────────────┘
       |
       ├── PASS → allow file write → continue
       |
       └── FAIL → rollback to SAVEPOINT
                → Feedback Synthesis Engine
                → structured JSON feedback → agent context
```

---

## Architecture: Two Interception Points

### Point 1 — Conversation Layer (North-South)

Detent intercepts all LLM API traffic between the user/IDE and the agent, implemented as an HTTP reverse proxy. When the agent's LLM response contains tool calls (file writes, bash execution), Detent sees them before the agent executes them.

**Mechanism:** Set `ANTHROPIC_BASE_URL` (Claude Code) or `OPENAI_BASE_URL` (Cursor, Codex CLI) to route through Detent's proxy. Point 1 response parsing is selected from the resolved upstream provider, not from the configured agent name.

**What it sees:** Full tool call intent before any filesystem change.

**Important:** Point 1 is observational only. The proxy can parse tool intent from
LLM API responses and run speculative verification for visibility/IPC, but it does
not block or rewrite the forwarded response. Enforcement remains Point 2.

### Point 2 — Tool Execution Layer (East-West)

Detent intercepts individual tool calls via agent-specific adapters before they hit the filesystem. This is the enforcement layer.

**Mechanism:** Agent-specific (PreToolUse hooks, MCP proxy, LiteLLM callbacks, event stream subscriptions — see Adapter Matrix below).

**What it does:** Intercepts, verifies, then allows / blocks-and-rolls-back / modifies the call.

---

## Agent Adapter Matrix

**HTTP adapters** (interception via API base URL override):

| Agent           | Interception Mechanism                        | Module                          | Status |
| --------------- | --------------------------------------------- | ------------------------------- | ------ |
| **Claude Code** | `PreToolUse`/`PostToolUse` hooks + HTTP proxy | `adapters/http/claude_code.py`  | ✅     |
| **Cursor**      | Provider-aware HTTP proxy adapter (`OpenAI` + `Anthropic` upstreams) | `adapters/http/cursor.py`       | ✅     |
| **Codex CLI**   | OpenAI-compatible HTTP proxy adapter with Responses API parsing | `adapters/http/codex.py`        | ✅     |

**Hook adapters** (preToolUse/callback hooks):

| Agent       | Interception Mechanism                              | Module                        | Status |
| ----------- | --------------------------------------------------- | ----------------------------- | ------ |
| **Gemini**  | HTTP hook adapter (`/hooks/gemini`)                 | `adapters/hook/gemini.py`     | ✅     |
| **LiteLLM** | Callback hook (observability-only; no rollback)     | `adapters/hook/litellm.py`    | ✅     |
| **OpenAPI** | Generic HTTP hook adapter (`/hooks/openapi`)        | `adapters/hook/openapi.py`    | ✅     |

**Graph adapters**:

| Agent        | Interception Mechanism                                      | Module                  | Status |
| ------------ | ----------------------------------------------------------- | ----------------------- | ------ |
| **LangGraph** | `VerificationNode` inserted into graph + LangChain callback | `adapters/langgraph.py` | ✅     |

**Planned adapters**:

| Agent                | Interception Mechanism                        | Status |
| -------------------- | --------------------------------------------- | ------ |
| **Aider**            | LiteLLM callback injection + `Coder` subclass | ❌     |
| **Cline / Roo Code** | MCP stdio proxy + `.clinerules`/hooks         | ❌     |
| **OpenHands**        | Event stream subscription + REST API          | ❌     |

### Claude Code Adapter

Claude Code's `PreToolUse` hook receives the full proposed file content as JSON on stdin before any disk write. Detent's hook can:

- **Block** (exit code 2): triggers rollback and injects feedback via `additionalContext`
- **Allow** (exit code 0): write proceeds
- **Modify** (via `updatedInput`): rewrite the tool input before execution

```json
// PreToolUse stdin (received by Detent's hook)
{
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/src/main.py",
    "content": "..."
  }
}
```

### Gemini Adapter

Gemini CLI's `BeforeTool` hook posts a JSON payload with `tool_name` and `tool_input`
before a tool executes. Detent normalizes that shape directly and retains a fallback
for older `functionCall` / `function_call`-style payloads when present.

### LangGraph Adapter (VerificationNode)

Insert `VerificationNode` into any LangGraph graph to gate all file writes made by that agent:

```python
from detent.adapters.langgraph import VerificationNode
from detent import DetentProxy

proxy = DetentProxy.from_config("detent.yaml")

# Insert into graph between agent node and any downstream nodes
graph.add_node("verify", VerificationNode(proxy))
graph.add_edge("agent", "verify")
graph.add_edge("verify", "tools")
```

The `VerificationNode` integrates with LangGraph's native checkpointing — rollback state is stored in the same backend as conversation state.

---

## Checkpoint Engine & Rollback

Every tool call that modifies the filesystem creates a **SAVEPOINT** before execution, following SQL transaction semantics applied to file operations.

### What the checkpoint engine maintains

| Component                  | Description                                                                                     | Latency            |
| -------------------------- | ----------------------------------------------------------------------------------------------- | ------------------ |
| **In-memory SAVEPOINTs**   | Named checkpoints (`before_write_004`) with file content snapshots                              | <1ms creation      |
| **Shadow git repository**  | Durable backup of each checkpoint, separate from the project's main git history                 | <500ms commit      |
| **Git worktree isolation** | Each agent session in its own worktree, preventing cross-session pollution                      | Near-instantaneous |
| **Partial rollback**       | ROLLBACK TO SAVEPOINT semantics — rollback only the failing call, preserve prior verified state | <500ms             |

### Rollback flow

```
1. Agent issues Write tool call
2. Checkpoint engine creates SAVEPOINT (snapshot in-memory + shadow git commit)
3. Verification pipeline runs on proposed content
4. If FAIL:
   a. Checkpoint engine rolls back to SAVEPOINT (restores file content)
   b. Feedback synthesis engine generates structured feedback
   c. Feedback injected into agent context (additionalContext / tool result)
   d. Agent retries with feedback
5. If PASS:
   a. File write executed
   b. SAVEPOINT retained in audit log
   c. Agent continues
```

### Manual rollback (CLI)

```bash
detent rollback                    # rollback last SAVEPOINT
detent rollback before_write_004   # rollback to named checkpoint
detent status                      # show current session checkpoint state
```

---

## Verification Pipeline

Stages are composable and configured via `detent.yaml`. They run sequentially by default; parallel execution is configurable for independent stages.

### Stages (v1.0 — multi-language)

| Stage                       | Tools                                                   | Languages                                        |
| --------------------------- | ------------------------------------------------------- | ------------------------------------------------ |
| **Syntax validation**       | tree-sitter                                             | Python, JavaScript/TypeScript, Rust, Go          |
| **Linting**                 | Ruff, ESLint, Clippy, go vet                            | Python (ruff), JS/TS (eslint), Rust (clippy), Go (go vet) |
| **Type checking**           | mypy, tsc, cargo check, go build                        | Python (mypy), TypeScript (tsc), Rust (cargo check), Go (go build) |
| **Targeted test execution** | pytest, jest, cargo test, go test                       | Python (pytest), JS/TS (jest), Rust (cargo test), Go (go test) |
| **Security scanning** ✅    | Bandit + Semgrep (configurable rulesets)                | Python + multi-language (semgrep)                |

### Future Stages (v1.x)

| Stage                 | Tools                                                          |
| --------------------- | -------------------------------------------------------------- |
| **Dependency audit**  | pip-audit, npm audit, hallucinated package detection           |
| **Test generation**   | LLM-assisted test scaffold for uncovered code paths (optional) |

### detent.yaml configuration

```yaml
stages:
  - name: syntax
    enabled: true
  - name: lint
    enabled: true
  - name: typecheck
    enabled: true
    timeout: 30s
  - name: tests
    enabled: true
    timeout: 60s
  - name: security
    enabled: true
    timeout: 30
    options:
      semgrep:
        enabled: true
        rulesets:
          - p/python
          - p/owasp-top-ten
      bandit:
        enabled: true
        confidence: low

policy: standard # strict | standard | permissive
agent: claude-code # detected automatically by `detent init`
```

### Policy profiles (P1)

| Profile      | Behavior                                            |
| ------------ | --------------------------------------------------- |
| `strict`     | All stages enabled; any finding blocks the write    |
| `standard`   | P0 stages enabled; warnings do not block, errors do |
| `permissive` | Syntax only; all other stages as warnings           |

---

## Feedback Synthesis Engine

When verification fails, Detent does **not** return raw linter/tool output. Raw errors (stack traces, lint dumps) are not structured for LLM consumption. Detent synthesizes findings into structured, LLM-optimized feedback.

### Synthesis steps

1. **Root cause localization:** maps failures back to the specific lines in the proposed diff, not the downstream error location
2. **Severity prioritization:** ranks findings by impact (blocking errors before style warnings) within the agent's token budget
3. **Context extraction:** includes relevant surrounding code for each finding
4. **Natural language summary:** concise, actionable repair instruction in plain English
5. **Fix suggestion:** where deterministic (syntax errors, type mismatches), provides the corrected code directly

### Feedback format (JSON, Claude Code `additionalContext`-compatible)

```json
{
  "status": "blocked",
  "checkpoint": "before_write_004",
  "summary": "Type error in /src/main.py line 42: argument of type 'str' is not compatible with 'int'.",
  "findings": [
    {
      "stage": "typecheck",
      "severity": "error",
      "file": "/src/main.py",
      "line": 42,
      "message": "Argument 1 to \"process\" has incompatible type \"str\"; expected \"int\"",
      "context": "...",
      "fix_suggestion": "Cast the argument: process(int(user_input))"
    }
  ],
  "rollback_applied": true
}
```

---

## Normalized Action Schema

All intercepted events are normalized to a common schema (derived from OpenTelemetry GenAI semantic conventions) regardless of which agent adapter produced them:

```python
class AgentAction:
    action_type: Literal["file_write", "shell_exec", "file_read", "web_fetch", "mcp_tool"]
    agent: Literal["claude-code", "cursor", "aider", "cline", "openhands", "codex", "langgraph"]
    tool_name: str          # e.g. "Write", "Bash", "Edit"
    tool_input: dict        # raw tool input (file_path, content, etc.)
    tool_call_id: str       # e.g. "toolu_01ABC..."
    session_id: str         # e.g. "sess_abc123"
    checkpoint_ref: str     # e.g. "chk_before_write_004"
    risk_level: Literal["low", "medium", "high"]
```

The pipeline always receives `AgentAction`, never raw agent-specific payloads. This is what makes new agent adapters cheap to add — implement the normalization once, the pipeline runs unchanged.

---

## Python SDK

Detent ships a first-class Python SDK for programmatic use (especially LangGraph and Aider integrations).

```python
from detent import DetentProxy, VerificationPipeline, VerificationStage

# Initialize from config file
proxy = DetentProxy.from_config("detent.yaml")

# Or build pipeline programmatically
pipeline = VerificationPipeline([
    VerificationStage.syntax(),
    VerificationStage.lint(tools=["ruff"]),
    VerificationStage.typecheck(tools=["mypy"]),
    VerificationStage.tests(pattern="modified"),
])

proxy = DetentProxy(pipeline=pipeline)

# Manually verify a file (CLI equivalent of `detent run <file>`)
result = await proxy.verify_file("/src/main.py", content="...")
if result.status == "blocked":
    print(result.summary)
```

All SDK methods are **async**.

---

## Adding New Verification Stages

### 1. Implement `VerificationStage`

Stages are organized as subdirectories. Create a `base.py` for the stage dispatcher and language-specific helper files as needed:

```
detent/stages/my_stage/
├── base.py           # Stage dispatcher (routes to language-specific helpers)
├── _python.py        # Python-specific logic (optional)
└── _typescript.py    # TypeScript-specific logic (optional)
```

```python
# detent/stages/my_stage/base.py
from detent.stages.base import VerificationStage, VerificationResult, Finding

class MyCustomStage(VerificationStage):
    """Example custom verification stage."""

    name = "my_stage"

    async def run(self, action: AgentAction) -> VerificationResult:
        """Run verification on the proposed action."""
        findings = []

        # Inspect action.tool_input["content"] or action.tool_input["file_path"]
        content = action.tool_input.get("content", "")
        file_path = action.tool_input.get("file_path", "")

        # Run your checks
        if "TODO" in content:
            findings.append(Finding(
                severity="warning",
                file=file_path,
                line=content.find("TODO"),
                message="TODO comment left in code",
            ))

        return VerificationResult(
            stage=self.name,
            passed=not any(f.severity == "error" for f in findings),
            findings=findings,
        )
```

### 2. Register via entry point (pip-installable plugin, P1)

```toml
# pyproject.toml of your plugin package
[project.entry-points."detent.stages"]
my_stage = "my_package.stages:MyCustomStage"
```

### 3. Enable in detent.yaml

```yaml
stages:
  - name: my_stage
    enabled: true
```

### 4. Write unit tests

```python
# tests/unit/test_my_stage.py
import pytest
from detent.stages.my_stage import MyCustomStage
from detent.schema import AgentAction

@pytest.mark.asyncio
async def test_my_stage_blocks_todos():
    stage = MyCustomStage()
    action = AgentAction(
        action_type="file_write",
        agent="claude-code",
        tool_name="Write",
        tool_input={"file_path": "/src/main.py", "content": "# TODO: fix this"},
        ...
    )
    result = await stage.run(action)
    assert len(result.findings) == 1
    assert result.findings[0].message == "TODO comment left in code"
```

---

## Adding New Agent Adapters

### 1. Implement the adapter

```python
# detent/adapters/my_agent.py
from detent.adapters.base import AgentAdapter
from detent.schema import AgentAction

class MyAgentAdapter(AgentAdapter):
    """Adapter for MyAgent."""

    agent_name = "my-agent"

    async def intercept(self, raw_event: dict) -> AgentAction:
        """Normalize agent-specific event to AgentAction."""
        return AgentAction(
            action_type="file_write",
            agent=self.agent_name,
            tool_name=raw_event["tool"],
            tool_input=raw_event["input"],
            tool_call_id=raw_event["id"],
            session_id=self.session_id,
            checkpoint_ref=self.checkpoint_engine.current_ref(),
            risk_level="medium",
        )

    async def inject_feedback(self, result: VerificationResult) -> None:
        """Inject structured feedback back into the agent's context."""
        # Agent-specific mechanism for feedback injection
        ...
```

### 2. Register adapter

```python
# detent/adapters/__init__.py
ADAPTERS = {
    "claude-code": ClaudeCodeAdapter,
    "cursor": CursorAdapter,
    "codex": CodexAdapter,
    "langgraph": LangGraphAdapter,
    "litellm": LiteLLMAdapter,
    "gemini": GeminiAdapter,
    "openapi": OpenAPIAdapter,
    "my-agent": MyAgentAdapter,   # add here
}
```

### 3. Write tests

Mock the agent's raw event format and verify normalization produces correct `AgentAction`.

---

## Implementation Details

### HTTP Proxy (`DetentProxy`)

Located: `detent/proxy/http_proxy.py`

- Listens on `127.0.0.1:{DETENT_PROXY_PORT}` (default 7070)
- Forwards requests transparently to upstream LLM API (`DETENT_PROXY_UPSTREAM`)
- Extracts tool use blocks from Anthropic/OpenAI-compatible API responses before returning to client
- Selects the Point 1 response parser from the configured upstream host (`proxy.upstream_url`) or the agent fallback
- Supports OpenAI chat-completions `tool_calls` and OpenAI Responses API `output[]` tool items for Codex/OpenAI-compatible clients
- Runs speculative pipeline observation on parsed file-write intents when an HTTP adapter + session manager are wired
- Never blocks or rewrites the forwarded response; all Point 1 observation is best-effort and non-fatal
- Implements retry logic with exponential backoff (3 retries: 100ms, 200ms, 400ms)
- Request timeout: `DETENT_PROXY_TIMEOUT_S` (default 5s)
- Persists session state to `.detent/session/default.json`
- Health endpoint: `GET /health` → `{"status": "ok"}`

**Key Methods:**
- `start()` / `stop()` — server lifecycle
- `_forward_with_retry(...)` — forward with retry logic

### IPC Control Channel (`IPCControlChannel`)

Located: `detent/ipc/channel.py`

- Unix domain socket at `.detent/run/control.sock` (configurable)
- NDJSON protocol: each message is JSON + `\n`
- Timeout: `DETENT_IPC_TIMEOUT_MS` (default 4000ms)

**Message Types:**
- `session_start` — session created
- `tool_intercepted` — tool call extracted, awaiting verification
- `verification_result` — pipeline result (pass/fail)
- `rollback_instruction` — rollback command + feedback
- `session_error` — error during verification
- `session_end` — session closed

**Key Methods:**
- `start_server()` / `stop_server()` — server lifecycle
- `send_message(msg)` — broadcast message to all clients
- `serialize_message(msg)` — NDJSON encoding

### Session Manager (`SessionManager`)

Located: `detent/proxy/session.py`

Orchestrates checkpoint + pipeline + IPC messaging:

- `start_session(session_id)` — initialize session, raise `DetentSessionConflictError` if active
- `intercept_tool_call(action)` → creates checkpoint → runs pipeline → on fail: rollback + IPC notification
- `end_session()` — clean up, close IPC

Integrates:
- `CheckpointEngine` for SAVEPOINT management
- `VerificationPipeline` for verification stages
- `IPCControlChannel` for async messaging
- `FeedbackSynthesizer` for LLM-optimized feedback

### Configuration

Environment variables override defaults in `detent.yaml`:

```bash
DETENT_PROXY_PORT=7070                      # Proxy listen port
DETENT_PROXY_UPSTREAM=https://api.anthropic.com
DETENT_PROXY_TIMEOUT_S=5                   # Request timeout
DETENT_IPC_SOCKET=.detent/run/control.sock
DETENT_IPC_TIMEOUT_MS=4000
DETENT_SESSION_DIR=.detent/session
```

`detent.yaml` may also set `proxy.upstream_url` explicitly when the agent name alone
is not enough to determine the provider. This is how Cursor can target Anthropic vs
OpenAI correctly. Google-backed Cursor traffic is not covered in v1.0.5.

### Testing

**Unit tests:**
- `tests/unit/test_http_proxy.py` — proxy forwarding, tool extraction, retry logic, health endpoint
- `tests/unit/test_ipc_channel.py` — NDJSON serialization, connection lifecycle, timeout
- `tests/unit/test_session_manager.py` — session lifecycle, checkpoint creation, pipeline integration

**Integration tests:**
- `tests/integration/test_proxy_ipc_full_flow.py` — full flow with real checkpoint engine and pipeline

**Coverage:** 324 tests total, >85% coverage for proxy, IPC, session manager

---

## Testing Stages & Adapters

### Unit tests

- Test each stage in isolation with mock `AgentAction` objects
- Test pass and fail cases for each check
- Test edge cases: empty content, binary files, very large files
- Aim for >80% coverage

```bash
uv run pytest tests/unit/ -v
uv run pytest tests/unit/test_syntax_stage.py -v
uv run pytest tests/unit/test_checkpoint_engine.py -v
```

### Integration tests

```bash
uv run pytest tests/integration/ -v
```

- Test full pipeline flow: action → checkpoint → verify → rollback
- Test end-to-end with a real (sandboxed) agent session

---

## Development Standards

### Code quality

- Each stage has a single, well-defined responsibility
- Extract complex logic into helper methods; DRY across stages
- Use type hints everywhere; async/await for all I/O
- Remove dead code and unused imports

### Logging

```python
import logging
logger = logging.getLogger(__name__)

# Required log points in each stage:
logger.info(f"[{self.name}] Starting verification for {action.tool_input.get('file_path')}")
logger.debug(f"[{self.name}] Running tool: {cmd}")
logger.info(f"[{self.name}] Completed: {'PASS' if result.passed else 'FAIL'} ({len(result.findings)} findings)")
```

### Error handling

```python
async def run(self, action: AgentAction) -> VerificationResult:
    try:
        findings = await self._run_tool(action)
    except Exception as e:
        logger.error(f"[{self.name}] Tool execution failed: {e}")
        # Do not crash the pipeline — return a safe error finding
        return VerificationResult(
            stage=self.name,
            passed=False,
            findings=[Finding(severity="error", message=f"Stage failed to run: {e}")],
        )
```

### Tool output parsing

- Verify tool output parsing matches actual tool schemas (mypy JSON, Ruff JSON, Semgrep JSON, etc.) against real tool output — not fictional/mocked schemas
- Test with known-bad and known-good code to catch parsing regressions early
- All subprocess calls must use async I/O (`asyncio.create_subprocess_exec`)

---

## Release Milestones

### v0.1 — Proof of Concept ✅ Complete

- [x] Dual-point proxy for Claude Code (HTTP proxy + PreToolUse/PostToolUse hooks)
- [x] LangGraph `VerificationNode`
- [x] Checkpoint engine: in-memory SAVEPOINTs + shadow git backup
- [x] Verification pipeline: syntax, linting, type checking, targeted tests
- [x] Feedback synthesis engine: root cause localization + structured JSON output
- [x] Atomic rollback on verification failure
- [x] `detent.yaml` configuration
- [x] `detent init` CLI for Claude Code
- [x] Python SDK: `DetentProxy`, `VerificationPipeline`, `VerificationStage`
- [x] Unit tests for `VerificationPipeline` and `CheckpointEngine`

### v1.0 — Production Ready ✅ Complete

- [x] All 7 agent adapters (HTTP: Claude Code, Cursor, Codex; Hook: Gemini, LiteLLM, OpenAPI; Graph: LangGraph)
- [x] Security scanning pipeline (Bandit + Semgrep)
- [x] Multi-language support: Python, JavaScript/TypeScript, Rust, Go
- [x] Observability: OpenTelemetry traces and metrics (`detent/observability/`)
- [x] Circuit breaker (`detent/circuit_breaker.py`)
- [x] Policy profiles (strict, standard, permissive)
- [x] 324 tests

### v2.0 — Enterprise Platform (12 months)

- Detent Cloud: managed SaaS, SSO, RBAC, audit dashboard
- Multi-agent session orchestration
- VS Code extension

---

## References

### Internal Documentation

- [docs/PRD.docx](./docs/PRD.docx) — Product Requirements Document (full feature requirements)
- [docs/SRS.docx](./docs/SRS.docx) — Software Requirements Specification
- [docs/ADD.docx](./docs/ADD.docx) — Architecture & Design Document
- [CLAUDE.md](./CLAUDE.md) — Claude Code–specific agent guidance
- [GEMINI.md](./GEMINI.md) — Gemini-specific agent guidance

### External Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [Claude Code hooks documentation](https://docs.anthropic.com/en/docs/claude-code/hooks)
- [OpenTelemetry GenAI semantic conventions](https://opentelemetry.io/docs/specs/semconv/gen-ai/)
- [tree-sitter](https://tree-sitter.github.io/tree-sitter/)
- [Ruff](https://docs.astral.sh/ruff/)
- [mypy](https://mypy.readthedocs.io/)
- [Semgrep](https://semgrep.dev/docs/)
- [Bandit](https://bandit.readthedocs.io/)

---

## CLI & SDK

### CLI Commands

The `detent` command provides four operations:

**1. `detent init`** — Interactive setup
- Detects agent type (claude-code, langgraph, cursor, aider)
- Prompts for policy profile (strict, standard, permissive)
- Creates `detent.yaml` and `.detent/session/` directory
- Example:
  ```bash
  $ detent init
  ✨ Detent Configuration Wizard
  Detected agent: claude-code
  Is this correct? [Y/n]: Y
  Select policy profile: [1-3]: 2
  ✓ Created detent.yaml
  ```

**2. `detent run <file>`** — Verify a file
- Loads config from `detent.yaml`
- Creates checkpoint before running pipeline
- Executes full verification pipeline (syntax → lint → typecheck → tests)
- Rolls back automatically if verification fails (unless policy allows)
- Returns exit code 0 (pass) or 1 (fail)
- Example:
  ```bash
  $ detent run src/main.py
  🔍 Running verification pipeline for src/main.py
  [████████████] syntax ✓
  [████████████] lint ✓
  [████████████] typecheck ✓
  [████████████] tests ✓
  ✅ All stages passed
  Checkpoint: chk_before_write_000
  ```

**3. `detent status`** — Show session state
- Displays active session ID
- Lists all checkpoints with status (created, rolled_back, restored)
- Example:
  ```bash
  $ detent status
  📊 Detent Session Status
  Session: sess_abc123def456
  Checkpoints: 2
    chk_before_write_000  src/main.py    ✓ created
    chk_before_write_001  src/utils.py   ✗ rolled_back
  ```

**4. `detent rollback <ref>`** — Restore a checkpoint
- Looks up checkpoint by reference
- Calls CheckpointEngine.rollback() to restore file
- Updates session state
- Example:
  ```bash
  $ detent rollback chk_before_write_001
  🔄 Rolling back to chk_before_write_001 (src/utils.py)
  ✓ Restored src/utils.py to chk_before_write_001
  ```

### Session State

Session state is stored in `.detent/session/default.json`:

```json
{
  "session_id": "sess_abc123def456",
  "agent": "claude-code",
  "policy": "standard",
  "active": true,
  "started_at": "2026-03-08T14:22:15Z",
  "last_updated": "2026-03-08T14:25:33Z",
  "checkpoints": [
    {
      "ref": "chk_before_write_000",
      "file": "src/main.py",
      "created_at": "2026-03-08T14:22:16Z",
      "status": "created"
    }
  ]
}
```

### SDK Exports

The full SDK is now exportable from `detent`:

```python
from detent import (
    # Configuration
    DetentConfig, ProxyConfig, PipelineConfig, StageConfig,
    # Schema
    AgentAction, ActionType, RiskLevel,
    # Runtime
    DetentProxy, SessionManager, IPCControlChannel,
    # Checkpoint
    CheckpointEngine,
    # Pipeline
    VerificationPipeline, VerificationResult, Finding,
    # Feedback
    FeedbackSynthesizer, StructuredFeedback, EnrichedFinding,
    # Stages
    VerificationStage, SyntaxStage, LintStage, TypecheckStage, TestsStage,
    # Adapters
    AgentAdapter, ClaudeCodeAdapter, CursorAdapter, CodexAdapter,
    LangGraphAdapter, LiteLLMAdapter, GeminiAdapter, OpenAPIAdapter,
    HTTPProxyAdapter, HookAdapter,
    # Types
    DetentSessionConflictError, IPCMessageType,
)
```

### Testing CLI

Unit tests for CLI components:
- `tests/unit/test_cli_session.py` — SessionManager persistence and tracking
- `tests/unit/test_cli_init.py` — Agent detection and setup
- `tests/unit/test_cli_run.py` — File verification and pipeline integration
- `tests/unit/test_cli_status_rollback.py` — Status display and checkpoint restoration
- `tests/unit/test_cli_commands.py` — Click command help and entry points
- `tests/unit/test_sdk_exports.py` — SDK export completeness

Integration test:
- `tests/integration/test_cli_workflow.py` — Full end-to-end workflow

---

**Last Updated:** 2026-03-25
**Version:** 1.0.0
