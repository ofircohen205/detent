# Dual-Point Interception Model

## Why Two Points?

A single interception point is insufficient for full coverage:

- **HTTP proxy alone** is observational. It can read LLM API responses and extract intent, but it cannot block a tool call — the write has already been approved by the time the proxy response is forwarded.
- **Hook alone** enforces writes but lacks conversation context. Without seeing the LLM's full response, the hook cannot know *why* the agent wrote what it wrote.

Combining both gives Detent complete visibility and real enforcement power.

## Point 1: HTTP Reverse Proxy

The proxy runs on `127.0.0.1:7070` (configurable) and is activated by overriding the LLM API base URL in the agent's environment:

```bash
# Claude Code
export ANTHROPIC_BASE_URL=http://127.0.0.1:7070

# Codex CLI
export OPENAI_BASE_URL=http://127.0.0.1:7070
```

### What the proxy does

1. **Receives** the agent's API request
2. **Forwards** it to the real upstream (`api.anthropic.com` or `api.openai.com`) via `_forward_with_retry` with 3-attempt exponential backoff
3. **Records** the conversation context in `SessionManager` via `observe_tool_call()`
4. **Returns** the upstream response verbatim to the agent (the proxy does not alter LLM responses)

The proxy is intentionally **observational-only**. It never modifies the LLM's output or injects content. Its purpose is to correlate conversation context with the tool calls that Point 2 sees.

### Strict mode

When `strict_mode: true` in `detent.yaml`, the proxy becomes fail-closed: if the circuit breaker is open (upstream unreachable), the proxy returns HTTP 503 instead of letting the request bypass Detent. Default is `false` (fail-open) to avoid breaking agent sessions.

### Security

The proxy uses `_ALLOWED_UPSTREAM_HOSTS` (a frozenset containing `api.anthropic.com` and `api.openai.com`) to prevent SSRF. Requests targeting unlisted hosts are rejected with a generic 502.

## Point 2: Agent Hooks (Enforcement Layer)

This is what actually blocks writes. Each agent uses a different hook mechanism:

| Agent | Mechanism | Config location |
|-------|-----------|-----------------|
| Claude Code | `PreToolUse` hook | `~/.claude/settings.json` |
| Codex CLI | pre-exec hook | `.codex/hooks.json` |
| Gemini CLI | `BeforeTool` hook | `GEMINI.md` |
| LangGraph | `VerificationNode` (code) | In-process |

When a file-write tool call fires, the hook adapter:

1. Receives the raw tool call event
2. Calls `intercept(raw_event)` to normalize it to `AgentAction`
3. Calls `intercept_tool_call(action)` which: creates a SAVEPOINT, runs the pipeline, and either allows or rolls back
4. Returns `permissionDecision: allow` or `permissionDecision: deny` to the agent

### File-write guard

Every hook adapter includes an adapter-level `FILE_WRITE` guard as defense-in-depth. Even if the hook matcher is mis-configured, only tool calls that normalize to `ActionType.FILE_WRITE` proceed to the pipeline.

For Claude Code, the matcher is `Write|Edit|NotebookEdit`. The adapter also checks `_ACTION_TYPE_MAP` internally. This means a misconfigured matcher that allows `Bash` through will still be filtered.

## Data Flow

```
AI Agent
    │
    │  API call (e.g. POST /v1/messages)
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  DetentProxy (Point 1)                                           │
│  aiohttp server on 127.0.0.1:7070                                │
│                                                                  │
│  1. _forward_with_retry(request)  →  upstream API               │
│  2. extract tool_calls from response                             │
│  3. SessionManager.observe_tool_call(session_id, tool_call)      │
│  4. return upstream response verbatim                            │
└──────────────────────────────────────────────────────────────────┘
    │
    │  IPC (Unix socket)
    │  IPCControlChannel sends observation to hook process
    ▼
┌──────────────────────────────────────────────────────────────────┐
│  Hook Adapter (Point 2)                                          │
│  ClaudeCodeHookAdapter / CodexHookAdapter / GeminiHookAdapter    │
│                                                                  │
│  1. intercept(raw_event) → AgentAction                           │
│  2. intercept_tool_call(action):                                 │
│     a. CheckpointEngine.savepoint(ref, files)                    │
│     b. VerificationPipeline.run(action)                          │
│     c. if passed → discard savepoint, return allow              │
│        if failed → rollback savepoint, return deny              │
│  3. FeedbackSynthesizer.synthesize(result, action)               │
│  4. return permissionDecision + StructuredFeedback               │
└──────────────────────────────────────────────────────────────────┘
    │
    ▼
  Filesystem (write allowed or blocked)
```

## AgentAction Normalization Boundary

All four adapters normalize their raw events to the same `AgentAction` schema before touching the pipeline:

```python
class AgentAction:
    action_type: Literal["file_write", "shell_exec", "file_read", "web_fetch", "mcp_tool"]
    agent: str           # "claude-code" | "codex" | "gemini" | "langgraph"
    tool_name: str       # "Write" | "Bash" | "write_file" | ...
    tool_input: dict     # raw tool input
    tool_call_id: str
    session_id: str
    checkpoint_ref: str  # "chk_before_write_004"
    risk_level: Literal["low", "medium", "high"]
```

The pipeline, checkpoint engine, and feedback synthesizer all operate on `AgentAction` exclusively. They have zero knowledge of which agent produced the event.

## Threat Model

**What dual-point catches:**

- File writes containing syntax errors (blocked before reaching disk)
- Lint violations or type errors in proposed code
- Test regressions triggered by the proposed change
- Hardcoded secrets and security vulnerabilities
- Dependency CVEs in requirements files

**Limitations:**

- Shell-based file creation via `Bash` is not currently intercepted for Codex (Codex exposes `Bash` rather than explicit file tools)
- Conversation-layer observability (Point 1) is not available for Gemini CLI (no base URL override mechanism)
- Detent does not intercept `git` operations, network calls, or process spawning

## See Also

- [Checkpoint Engine](./checkpoint-engine.md)
- [Verification Pipeline](./verification-pipeline.md)
- [Tutorial: Claude Code](../tutorials/02-claude-code.md)
