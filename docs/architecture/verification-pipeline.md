# Verification Pipeline

## Design Goals

1. **Composable** — stages are independent, ordered, and can be added or removed via config
2. **Language-aware** — each stage declares which languages it supports; unsupported languages are skipped cleanly
3. **Fail-fast** — once a stage reports errors, remaining stages are skipped (configurable)
4. **Never crashes the caller** — every stage exception is caught and converted to a safe error finding; the agent session must survive a Detent internal failure
5. **Async throughout** — all stage subprocess calls use `asyncio`, keeping proxy overhead low

## Stage Registry

Stages are registered in `detent/stages/__init__.py`:

```python
STAGE_REGISTRY: dict[str, type[VerificationStage]] = {
    "syntax":    SyntaxStage,
    "lint":      LintStage,
    "typecheck": TypecheckStage,
    "tests":     TestsStage,
    "security":  SecurityStage,
}
```

`VerificationPipeline.from_config(config)` uses the registry to instantiate stages:

```python
for stage_cfg in config.get_enabled_stages():
    stage_cls = STAGE_REGISTRY.get(stage_cfg.name)
    if stage_cls is None:
        logger.warning("[pipeline] unknown stage '%s'; skipping", stage_cfg.name)
        continue
    stages.append(stage_cls(stage_cfg))
```

Unknown stage names are skipped with a warning — a bad config entry does not crash the pipeline.

## Language Detection

`detect_language(file_path)` maps file extensions to language strings:

| Extension | Language |
|-----------|----------|
| `.py` | `python` |
| `.js`, `.jsx`, `.mjs` | `javascript` |
| `.ts`, `.tsx` | `typescript` |
| `.go` | `go` |
| `.rs` | `rust` |
| others | `unknown` |

Each stage overrides `supports_language(lang) -> bool`. The default implementation returns `True` (run on all languages). Language-specific stages (e.g., `_PytestStage`) return `True` only for `python`. The pipeline filters active stages before execution:

```python
active = [s for s in self._stages if s.supports_language(lang)]
```

## Sequential Execution (default)

```
for each stage in active:
    result = await stage.run(action)
    collected.append(result)
    if config.fail_fast and result.has_errors:
        break    ← skip remaining stages
```

`fail_fast=True` (default) halts after the first error-producing stage. Running typecheck after a lint stage has errors is wasteful — the agent will need to fix lint first anyway.

## Parallel Execution

When `pipeline.parallel: true` in `detent.yaml`:

```python
results = await asyncio.gather(*[s.run(action) for s in active])
```

All stages run concurrently. If `fail_fast=True`, results are truncated at the first error stage post-collection:

```python
truncated = []
for r in results:
    truncated.append(r)
    if r.has_errors:
        break
```

If `asyncio.gather` itself raises (unexpected), a synthetic pipeline-level error finding is returned instead of propagating the exception.

## Execution Flow

```
AgentAction
    │
    ▼
detect_language(file_path)
    │
    ▼
filter stages by supports_language()
    │
    ├── parallel=False ──► _run_sequential()
    │                         for each stage:
    │                           stage.run(action)
    │                           if fail_fast and has_errors: break
    │
    └── parallel=True  ──► _run_parallel()
                              asyncio.gather(all stages)
                              if fail_fast: truncate at first error
    │
    ▼
_aggregate(results)
    │
    ▼
VerificationResult(
    stage="pipeline",
    passed=not any(r.has_errors for r in results),
    findings=[all findings flattened],
    duration_ms=elapsed,
    metadata={"stage_results": [r.model_dump() for r in results]},
)
```

## VerificationStage Base Class

`VerificationStage.run(action)` is the public wrapper. It:

1. Records an OpenTelemetry span (`detent.stage.<name>`)
2. Calls `_run(action)` (the subclass implementation)
3. Catches **all exceptions** — returns a synthetic error finding instead of raising
4. Records Prometheus metrics: `record_stage_duration(stage_name, lang, passed, ms)`, `record_stage_findings(stage_name, count)`

Subclasses implement `_run(action) -> VerificationResult`. The `_subprocess.py` helper provides `run_subprocess(cmd, cwd, timeout)` with async process execution and structured stderr capture.

## Circuit Breaker

Each stage can be wrapped with a `CircuitBreaker` (configured via `StageConfig.circuit_breaker`):

```yaml
pipeline:
  stages:
    - name: tests
      circuit_breaker:
        enabled: true
        failure_threshold: 5    # open after 5 consecutive failures
        recovery_window_s: 60   # probe after 60 seconds in OPEN state
        behavior: warn          # "skip" or "warn" when open
```

States:

| State | Behaviour |
|-------|-----------|
| `CLOSED` | Normal operation — stage runs |
| `OPEN` | Stage is skipped or returns a warning finding (per `behavior`) |
| `HALF_OPEN` | One probe attempt — if it succeeds, closes; if it fails, reopens |

The circuit breaker protects the pipeline from a permanently broken external tool (e.g., mypy segfaulting) from blocking every write indefinitely.

## Adding a Custom Stage

1. Create `detent/stages/my_stage.py` implementing `VerificationStage`:

```python
from detent.stages.base import VerificationStage
from detent.pipeline.result import VerificationResult

class MyStage(VerificationStage):
    @property
    def name(self) -> str:
        return "my_stage"

    async def _run(self, action) -> VerificationResult:
        # ... run your tool, parse output, return findings
        return VerificationResult(stage=self.name, passed=True, findings=[], duration_ms=0)
```

2. Add to `detent/stages/__init__.py`:

```python
from detent.stages.my_stage import MyStage
STAGE_REGISTRY["my_stage"] = MyStage
```

3. Enable in `detent.yaml`:

```yaml
pipeline:
  stages:
    - name: my_stage
      enabled: true
      timeout: 30
```

## See Also

- [Checkpoint Engine](./checkpoint-engine.md)
- [Feedback Synthesis](./feedback-synthesis.md)
- [AGENTS.md: Adding New Verification Stages](../../AGENTS.md#adding-new-verification-stages)
