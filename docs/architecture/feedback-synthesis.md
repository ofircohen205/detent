# Feedback Synthesis Engine

## The Problem with Raw Tool Output

Linter and type checker stderr is not designed for machine consumption:

```
src/api.py:45:1: F821 undefined name 'authenticate'
src/api.py:67:20: E711 comparison to None (use 'is' or 'is not')
```

This format varies between tools (Ruff JSON vs ESLint vs mypy), mixes file paths with line numbers inconsistently, and lacks the source context an agent needs to understand *what to fix*. Injecting raw stderr into the agent's context degrades self-repair quality.

Detent converts raw `VerificationResult` findings into a single, structured `StructuredFeedback` object that agents can parse reliably.

## Synthesis Pipeline

`FeedbackSynthesizer.synthesize(result, action)` runs three steps:

```
VerificationResult.findings
    │
    ▼
1. Sort by severity (_SEVERITY_ORDER: error=0, warning=1, info=2)
    │
    ▼
2. Enrich each finding (_enrich):
   - For error-severity findings with a known line number and available content:
     extract ±3 lines of source context
    │
    ▼
3. Determine status + generate summary
    │
    ▼
StructuredFeedback
```

## Severity Ordering

Errors are sorted before warnings before info:

```python
_SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}
```

**Rationale:** An agent should fix errors before addressing warnings. Showing errors first ensures the most blocking issues are visible at the top of the findings list, regardless of which stage produced them or in which order stages ran.

## Finding Enrichment

`_enrich(finding, action)` adds source context for error-severity findings:

```
if finding.severity == "error"
   and finding.line is not None
   and action.content is not None:
    context_lines, context_start_line = _extract_context(content, finding.line, radius=3)
```

`_extract_context` returns the ±3 lines around the finding's line number (1-based). `context_start_line` is 1-based to match editor conventions.

Example: a finding at line 12 in a 20-line file returns lines 9–15 with `context_start_line=9`.

This eliminates the need for the agent to re-read the file — the relevant code is already in the feedback.

## Status Determination

`_determine_status(result)` maps the result to one of three strings:

| Condition | Status |
|-----------|--------|
| Any finding with `severity="error"` | `"blocked"` |
| Only warnings (no errors) | `"warning"` |
| No findings, or info only | `"passed"` |

## Summary Generation

`_generate_summary(result, action)` produces a single human-readable line:

- **No findings:** `"All verification checks passed for 'src/main.py'."`
- **With findings:** `` "`src/main.py`: 2 error(s) found in `lint` stage(s); 1 warning(s) from `typecheck` stage(s). File write blocked." ``

The summary aggregates counts by stage name so the agent knows *which* stages failed without reading every individual finding.

## StructuredFeedback Schema

```python
class StructuredFeedback:
    status: Literal["blocked", "warning", "passed"]
    checkpoint: str           # e.g. "chk_before_write_004"
    summary: str              # human-readable one-liner
    findings: list[EnrichedFinding]
    rollback_applied: bool    # set to True by SessionManager after rollback

class EnrichedFinding:
    severity: Literal["error", "warning", "info"]
    file: str | None          # relative or absolute path
    line: int | None          # 1-based line number
    column: int | None        # 1-based column number
    message: str              # human-readable description
    code: str | None          # linter rule code, e.g. "F821"
    stage: str                # which stage produced this finding
    fix_suggestion: str | None  # deterministic fix hint (where available)
    context_lines: list[str]  # ±3 lines of source context (empty if unavailable)
    context_start_line: int | None  # 1-based start line for context_lines
```

## Example Output

```json
{
  "status": "blocked",
  "checkpoint": "chk_before_write_004",
  "summary": "`src/api.py`: 2 error(s) found in `lint` stage(s). File write blocked.",
  "findings": [
    {
      "severity": "error",
      "file": "src/api.py",
      "line": 45,
      "column": 1,
      "message": "undefined name 'authenticate'",
      "code": "F821",
      "stage": "lint",
      "fix_suggestion": null,
      "context_lines": [
        "def handle_request(req):",
        "    user = authenticate(req)",
        "    return process(user)"
      ],
      "context_start_line": 44
    },
    {
      "severity": "error",
      "file": "src/api.py",
      "line": 67,
      "column": 20,
      "message": "comparison to None (use 'is' or 'is not')",
      "code": "E711",
      "stage": "lint",
      "fix_suggestion": null,
      "context_lines": [
        "    if result == None:",
        "        return default_response()"
      ],
      "context_start_line": 67
    }
  ],
  "rollback_applied": true
}
```

## Usage in SessionManager

`FeedbackSynthesizer.synthesize()` is called by `SessionManager` after the pipeline returns:

```python
feedback = synthesizer.synthesize(result, action)
feedback.rollback_applied = (not result.passed)  # set after rollback decision
ipc_channel.send(IPCMessageType.VERIFICATION_RESULT, feedback)
```

`rollback_applied` defaults to `False` in the synthesizer (it doesn't know whether rollback was triggered). `SessionManager` sets it to `True` after calling `engine.rollback(ref)`.

## Determinism

All synthesis is **fully deterministic** — no LLM calls, no randomness, no network I/O. The same `VerificationResult` always produces the same `StructuredFeedback`. This is intentional: v1.x prioritizes reliability and predictability over richer AI-generated suggestions.

LLM-assisted fix suggestions are a v2.0 roadmap item.

## See Also

- [Verification Pipeline](./verification-pipeline.md)
- [Checkpoint Engine](./checkpoint-engine.md)
