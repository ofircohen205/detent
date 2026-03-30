# Integrating Detent with Claude Code

This tutorial explains how Detent intercepts Claude Code file writes and walks you through the full setup.

## How Interception Works

Detent uses two integration points with Claude Code:

```
Claude Code
    │
    │ (LLM API traffic)
    ▼
┌──────────────────────────────────────┐
│ Point 1: HTTP Reverse Proxy          │  ← observational; records intent
│ ANTHROPIC_BASE_URL=http://127.0.0.1:7070   │
└──────────────────────────────────────┘
    │
    │ (tool calls)
    ▼
┌──────────────────────────────────────┐
│ Point 2: PreToolUse Hook             │  ← enforcement; blocks writes
│ ~/.claude/settings.json              │
└──────────────────────────────────────┘
    │
    ▼
  Filesystem
```

**Point 2 is what actually blocks writes.** The hook fires before every `Write`, `Edit`, or `NotebookEdit` call, runs the verification pipeline, and returns `permissionDecision: deny` if the code fails.

Point 1 is optional observability — it records the conversation context but does not modify LLM responses.

## Step 1: Initialize

```bash
cd my-project
detent init
```

`detent init` auto-detects Claude Code and writes the hook entry into `~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      {
        "matcher": "Write|Edit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "detent hook claude-code"
          }
        ]
      }
    ]
  }
}
```

The `matcher` is scoped to file-write tools only. Detent will not fire on `Bash`, `Read`, `WebFetch`, or other tools.

## Step 2: Start the Proxy (optional)

The proxy enables Point 1 observability:

```bash
export ANTHROPIC_BASE_URL=http://127.0.0.1:7070
detent proxy start
```

To skip the proxy and use enforcement-only mode, just omit the `ANTHROPIC_BASE_URL` override. The hook (Point 2) works independently.

## Step 3: Run a Claude Code Session

Open Claude Code in your project as usual. When Claude attempts a `Write` or `Edit`:

1. The PreToolUse hook fires
2. Detent creates a checkpoint SAVEPOINT
3. The verification pipeline runs (syntax → lint → typecheck → tests → security)
4. If all stages pass: `permissionDecision: allow` — the write proceeds
5. If any stage has errors: `permissionDecision: deny` — the write is blocked and the checkpoint is rolled back

### Example: blocked write

Claude Code output when a write is blocked:

```
Tool call denied by hook: Write
Reason: Verification failed — 2 error(s) in `lint` stage.
`src/api.py`: F821 undefined name 'authenticate' (line 45); E711 comparison to None (line 67).
File write blocked.
```

Claude Code automatically retries with the structured feedback, attempting to fix the issues.

## Hook Scope

The Claude Code adapter only intercepts tools matching `Write|Edit|NotebookEdit`:

| Tool | Intercepted |
|------|-------------|
| `Write` | ✅ Yes |
| `Edit` | ✅ Yes |
| `NotebookEdit` | ✅ Yes |
| `Bash` | ❌ No |
| `Read` | ❌ No |
| `WebFetch` | ❌ No |

Shell commands executed via `Bash` are not currently intercepted. Detent focuses on filesystem writes where verification is meaningful.

## Troubleshooting

**Hook is not firing**

- Verify the entry exists in `~/.claude/settings.json` under `PreToolUse`
- Confirm `detent` is on your `PATH`: `which detent`
- Check the matcher is exactly `Write|Edit|NotebookEdit`

**Port 7070 already in use**

Change the port in `detent.yaml`:

```yaml
proxy:
  port: 7071
```

Then update `ANTHROPIC_BASE_URL` to match.

**Hook fires but verification is skipped**

Check `detent.yaml` — if `pipeline.stages` is empty or all stages have `enabled: false`, no verification runs and all writes are allowed.

## See Also

- [Architecture: Dual-Point Interception](../architecture/dual-point-interception.md)
- [Architecture: Verification Pipeline](../architecture/verification-pipeline.md)
