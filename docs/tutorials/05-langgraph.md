# Integrating Detent with LangGraph

This tutorial shows how to drop `VerificationNode` into a LangGraph graph to gate file writes before they reach the filesystem.

## How It Works

LangGraph integration uses **Point 2 only** — there is no HTTP proxy or hook config. Everything is code-level: you wire `VerificationNode` into your graph as a node between the agent and its tools.

No `detent init` or `detent.yaml` changes are required (though `detent.yaml` is used if present).

## Step 1: Install

```bash
pip install detent langgraph
```

## Step 2: Create the VerificationNode

```python
import asyncio
from langgraph.graph import StateGraph, END
from detent import DetentConfig, VerificationPipeline
from detent.adapters.langgraph import LangGraphAdapter

# Load config (reads detent.yaml or uses defaults)
config = DetentConfig.load()
pipeline = VerificationPipeline.from_config(config)
adapter = LangGraphAdapter(pipeline=pipeline)
```

## Step 3: Wire Into Your Graph

```python
from langgraph.graph import StateGraph, END
from langgraph.prebuilt import ToolNode

# Your existing graph nodes
def agent_node(state):
    ...

def tools_node(state):
    ...

# Build graph
builder = StateGraph(AgentState)
builder.add_node("agent", agent_node)
builder.add_node("verify", adapter.as_node())   # ← insert Detent here
builder.add_node("tools", ToolNode(your_tools))

# Wire edges: agent → verify → tools (or END on deny)
builder.add_edge("agent", "verify")
builder.add_conditional_edges(
    "verify",
    route_after_verify,           # your routing function
    {"allow": "tools", "deny": END},
)
builder.add_edge("tools", "agent")
```

### Routing function

```python
def route_after_verify(state) -> str:
    last_message = state["messages"][-1]
    # Detent injects a ToolMessage with decision="deny" on failure
    if hasattr(last_message, "additional_kwargs"):
        if last_message.additional_kwargs.get("detent_decision") == "deny":
            return "deny"
    return "allow"
```

## What VerificationNode Intercepts

`VerificationNode` calls `adapter.intercept()` for each tool call in the graph state. It only verifies calls that satisfy both:

1. The tool name maps to a `FILE_WRITE` action (`Write`, `Edit`, `create_file`, etc.)
2. The file extension is a **verifiable language** (`.py`, `.js`, `.ts`, `.go`, `.rs`, and others in `detent/config/languages.py`)

Non-file-write tools and files with unsupported extensions pass through without verification.

## Customizing the Pipeline

To run only specific stages (e.g., skip tests for speed):

```python
from detent import DetentConfig, VerificationPipeline
from detent.config import PipelineConfig, StageConfig

config = DetentConfig(
    pipeline=PipelineConfig(
        fail_fast=True,
        stages=[
            StageConfig(name="syntax", enabled=True),
            StageConfig(name="lint", enabled=True),
            StageConfig(name="typecheck", enabled=True),
            # tests and security disabled for this graph
        ],
    )
)
pipeline = VerificationPipeline.from_config(config)
adapter = LangGraphAdapter(pipeline=pipeline)
```

## Session and Checkpoint Lifecycle

LangGraph tool calls often lack a `session_id`. Detent handles this gracefully:

- If `session_id` is missing from the raw event, `SessionManager` generates one automatically
- Each tool call gets its own `checkpoint_ref` (e.g., `chk_before_write_004`)
- On `deny`: the checkpoint is rolled back before returning
- On `allow`: the checkpoint is discarded (GC'd) after the write completes

## See Also

- [Architecture: Verification Pipeline](../architecture/verification-pipeline.md)
- [Architecture: Checkpoint Engine](../architecture/checkpoint-engine.md)
- [Getting Started](./01-getting-started.md)
