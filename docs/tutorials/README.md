# Detent Tutorials

Step-by-step guides for getting Detent working in your environment.

## Prerequisites

All tutorials assume:

- **Python 3.12+** — `python3 --version` should show 3.12.x or higher
- **Detent installed** — `pip install detent` (or `uv add detent`)
- **Your agent installed** — Claude Code, Codex CLI, Gemini CLI, or LangGraph

## Tutorials

| # | Guide | What you'll learn |
|---|-------|-------------------|
| 1 | [Getting Started](./01-getting-started.md) | Install, init, and intercept your first file write |
| 2 | [Claude Code](./02-claude-code.md) | Hook + proxy setup for Claude Code |
| 3 | [Codex CLI](./03-codex.md) | Hook + proxy setup for Codex CLI |
| 4 | [Gemini CLI](./04-gemini.md) | BeforeTool hook setup for Gemini CLI |
| 5 | [LangGraph](./05-langgraph.md) | Drop-in `VerificationNode` for LangGraph graphs |

## Suggested Order

New to Detent? Start with **Tutorial 1**, then jump to the tutorial for your agent.

Already know Detent? Jump directly to the agent-specific guide.
