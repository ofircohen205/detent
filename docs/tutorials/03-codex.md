# Integrating Detent with Codex CLI

This tutorial explains how Detent intercepts Codex CLI file writes using an HTTP proxy and a pre-execution hook.

## How Interception Works

Codex CLI integration mirrors Claude Code: an HTTP proxy for observability (Point 1) and a pre-exec hook for enforcement (Point 2).

```
Codex CLI
    │
    │ (OpenAI API traffic)
    ▼
┌──────────────────────────────────────┐
│ Point 1: HTTP Reverse Proxy          │  ← observational
│ OPENAI_BASE_URL=http://127.0.0.1:7070    │
└──────────────────────────────────────┘
    │
    │ (tool calls)
    ▼
┌──────────────────────────────────────┐
│ Point 2: Pre-exec Hook               │  ← enforcement
│ .codex/hooks.json                    │
└──────────────────────────────────────┘
    │
    ▼
  Filesystem
```

## Step 1: Initialize

```bash
cd my-project
detent init
```

`detent init` writes the hook configuration to `.codex/hooks.json` in your project directory:

```json
{
  "hooks": {
    "pre_tool_call": [
      {
        "matcher": "write_file|edit_file",
        "command": "detent hook codex"
      }
    ]
  }
}
```

> **v1.1 note:** The correct location is `.codex/hooks.json`. Earlier versions incorrectly used `.codex/instructions.md`. If you have a pre-v1.1 installation, `detent init` automatically migrates stale entries in-place.

## Step 2: Start the Proxy

```bash
export OPENAI_BASE_URL=http://127.0.0.1:7070
detent proxy start
```

The proxy forwards all requests to `api.openai.com` and records intent-level context for observability.

To skip the proxy and use enforcement-only mode, omit the `OPENAI_BASE_URL` override.

## Step 3: Run a Codex Session

With the hook in place, Codex CLI will call `detent hook codex` before each file write. Detent runs the pipeline and returns an approval decision:

**Approved write:**
```json
{ "approved": true }
```

**Blocked write:**
```json
{
  "approved": false,
  "decision": "deny",
  "reason": "Verification failed",
  "feedback": {
    "status": "blocked",
    "summary": "`src/main.py`: 1 error(s) found in `syntax` stage(s). File write blocked.",
    "findings": [ ... ]
  }
}
```

## Hook Payload Formats

The Codex hook adapter accepts three payload formats that Codex CLI may send:

**Nested format:**
```json
{
  "functionCall": {
    "name": "write_file",
    "arguments": { "path": "src/main.py", "content": "..." }
  }
}
```

**Flat format:**
```json
{
  "tool_name": "write_file",
  "tool_input": { "path": "src/main.py", "content": "..." }
}
```

**With-type format:**
```json
{
  "type": "tool_call",
  "tool_name": "write_file",
  "tool_input": { "path": "src/main.py", "content": "..." }
}
```

All three are normalized to the same `AgentAction` internally.

## Current Limitations

- Codex CLI exposes file writes as Bash commands in some configurations. Detent intercepts explicit `write_file` and `edit_file` tool calls; shell-based writes via `Bash` are not yet intercepted.
- Point 1 (proxy) requires `OPENAI_BASE_URL` support in your Codex CLI version. Check `codex --help` to confirm the flag is available.

## See Also

- [Architecture: Dual-Point Interception](../architecture/dual-point-interception.md)
- [Getting Started](./01-getting-started.md)
