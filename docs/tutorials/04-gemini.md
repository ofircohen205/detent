# Integrating Detent with Gemini CLI

This tutorial explains how Detent intercepts Gemini CLI file writes using a BeforeTool hook.

## How Interception Works

Gemini CLI integration uses **Point 2 only** (enforcement hook). Unlike Claude Code and Codex, Gemini CLI does not expose a base URL override, so the HTTP proxy (Point 1) is not available.

```
Gemini CLI
    │
    │ (tool calls)
    ▼
┌──────────────────────────────────────┐
│ Point 2: BeforeTool Hook             │  ← enforcement (only integration point)
│ GEMINI.md hook config                │
└──────────────────────────────────────┘
    │
    ▼
  Filesystem
```

This means Detent protects the filesystem against bad writes, but has no conversation-layer observability for Gemini.

## Step 1: Initialize

```bash
cd my-project
detent init
```

`detent init` writes the Gemini hook configuration. Gemini CLI reads hook config from `GEMINI.md` in your project root:

```markdown
<!-- detent:hook:start -->
Before calling write_file or edit, run:
  detent hook gemini
<!-- detent:hook:end -->
```

The adapter intercepts Gemini's native tool names: **`write_file`** and **`edit`** (not Claude Code's `Write`/`Edit`).

## Step 2: Run a Gemini Session

With the hook configured, Gemini CLI calls `detent hook gemini` before each file write. The hook receives a FunctionCall payload and returns an allow/deny decision.

## Accepted Payload Formats

The Gemini hook adapter accepts two FunctionCall formats:

**Nested camelCase format:**
```json
{
  "functionCall": {
    "name": "write_file",
    "args": { "path": "src/main.py", "content": "..." }
  }
}
```

**Nested snake_case format:**
```json
{
  "function_call": {
    "name": "write_file",
    "args": { "path": "src/main.py", "content": "..." }
  }
}
```

Both are normalized identically.

**Non-file-write tools** (e.g., `read_file`, `run_shell`) return `None` from `intercept()` and are allowed through without verification.

## Tool Name Mapping

Gemini uses different tool names than Claude Code. The Gemini adapter maps:

| Gemini tool name | Detent action type |
|------------------|--------------------|
| `write_file` | `FILE_WRITE` |
| `edit` | `FILE_WRITE` |
| all others | *(skipped — no action)* |

## Limitations

- **No Point 1 (proxy)**: Conversation-layer observability is not available for Gemini CLI.
- **Hook-only**: The BeforeTool hook is the only enforcement mechanism.
- Gemini's tool names differ from Claude Code's; do not mix up `write_file` with `Write`.

## See Also

- [Architecture: Dual-Point Interception](../architecture/dual-point-interception.md)
- [Getting Started](./01-getting-started.md)
