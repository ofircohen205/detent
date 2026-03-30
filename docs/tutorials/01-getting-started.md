# Getting Started with Detent

This tutorial walks you through installing Detent, initializing it in a project, and watching it intercept a bad file write in real time.

## Prerequisites

- Python 3.12+
- A project directory (any language)

## Step 1: Install

```bash
# pip
pip install detent

# uv
uv add detent

# From source
git clone https://github.com/ofircohen205/detent
cd detent && uv sync
```

Verify the install:

```bash
detent --version
# detent 1.2.0
```

## Step 2: Initialize

Run `detent init` in your project root. The wizard auto-detects your agent and writes `detent.yaml`:

```bash
cd my-project
detent init
```

Example output:

```
Detected agent: claude-code
Written: detent.yaml
Written: ~/.claude/settings.json (hook registered)
Detent is ready. Start your agent and it will be protected automatically.
```

### What `detent.yaml` contains

```yaml
policy: standard          # strict | standard | permissive
agent: claude-code        # auto-detected

proxy:
  host: 127.0.0.1
  port: 7070

pipeline:
  fail_fast: true         # halt on first stage with errors
  parallel: false
  stages:
    - name: syntax        # tree-sitter parse check
      enabled: true
    - name: lint          # ruff / ESLint / clippy / go vet
      enabled: true
    - name: typecheck     # mypy / tsc / cargo check / go build
      enabled: true
      timeout: 30
    - name: tests         # pytest / jest / cargo test / go test
      enabled: true
      timeout: 60
    - name: security      # semgrep + bandit + detect-secrets + pip-audit
      enabled: true
      timeout: 30
```

## Step 3: Your First Interception

Create a Python file with a syntax error and let Detent block the write:

```python
# bad_code.py — intentional syntax error
def greet(name
    print(f"Hello, {name}")
```

Run verification manually:

```bash
detent run bad_code.py
```

Output:

```
✗ Verification failed for bad_code.py
  Stage:   syntax
  Status:  blocked

  Findings:
    ERROR  bad_code.py:2  SyntaxError: invalid syntax

  File write blocked. Checkpoint: chk_before_write_000
```

The file was not written to disk. The checkpoint was rolled back.

## Step 4: Understanding the Feedback

Detent returns structured JSON feedback to the agent. Here's what it looks like:

```json
{
  "status": "blocked",
  "checkpoint": "chk_before_write_000",
  "summary": "`bad_code.py`: 1 error(s) found in `syntax` stage(s). File write blocked.",
  "findings": [
    {
      "severity": "error",
      "file": "bad_code.py",
      "line": 2,
      "column": null,
      "message": "SyntaxError: invalid syntax",
      "code": null,
      "stage": "syntax",
      "fix_suggestion": null,
      "context_lines": ["def greet(name", "    print(f\"Hello, {name}\")"],
      "context_start_line": 1
    }
  ],
  "rollback_applied": true
}
```

The `context_lines` field gives the agent the surrounding code so it can self-repair without re-reading the file.

## Step 5: Policy Profiles

Control which stages run and whether findings are blocking:

| Profile | Behavior |
|---------|----------|
| `strict` | All stages enabled; any finding blocks the write |
| `standard` | All stages enabled; only error-severity findings block (default) |
| `permissive` | Syntax only; all other stages run as warnings |

Change the profile in `detent.yaml`:

```yaml
policy: strict
```

## Step 6: SDK Usage

You can drive Detent programmatically:

```python
import asyncio
from detent import DetentConfig, VerificationPipeline, AgentAction, ActionType, RiskLevel

async def main():
    config = DetentConfig.load()          # reads detent.yaml or uses defaults
    pipeline = VerificationPipeline.from_config(config)

    action = AgentAction(
        action_type=ActionType.FILE_WRITE,
        agent="my-agent",
        tool_name="Write",
        tool_input={"file_path": "src/main.py", "content": "def bad("},
        tool_call_id="tc_001",
        session_id="sess_001",
        checkpoint_ref="chk_before_write_000",
        risk_level=RiskLevel.MEDIUM,
    )

    result = await pipeline.run(action)
    print(result.passed, result.findings)

asyncio.run(main())
```

## Next Steps

- [Claude Code integration](./02-claude-code.md)
- [Codex CLI integration](./03-codex.md)
- [Gemini CLI integration](./04-gemini.md)
- [LangGraph integration](./05-langgraph.md)
