# Detent Architecture

These documents explain the design decisions behind each Detent subsystem — going deeper than the quick-start guides and the top-level AGENTS.md overview.

## Documents

| Document | What it covers |
|----------|----------------|
| [Dual-Point Interception](./dual-point-interception.md) | HTTP proxy + hook model, IPC channel, `AgentAction` normalization, threat model |
| [Checkpoint Engine](./checkpoint-engine.md) | SAVEPOINT semantics, in-memory snapshots, atomic restore, shadow git backup |
| [Verification Pipeline](./verification-pipeline.md) | Stage registry, language detection, sequential/parallel execution, circuit breakers |
| [Feedback Synthesis](./feedback-synthesis.md) | Raw tool output → structured LLM-optimized JSON, enrichment, determinism |

## Key Invariants

These invariants hold across all subsystems:

1. **Never crash the caller.** Every stage exception is caught and converted to a safe error finding. The agent session must survive a Detent internal failure.
2. **Rollback is atomic.** SAVEPOINT is created *before* the write. Rollback uses `os.replace()` (POSIX-atomic rename).
3. **Feedback quality over throughput.** Structured findings with source context outperform raw linter stderr for agent self-repair.
4. **Adapter-agnostic pipeline.** All four agent adapters normalize to `AgentAction` before the pipeline runs. The pipeline has no knowledge of which agent it's serving.
