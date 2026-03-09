# Development Guide

Everything you need to know to develop Detent locally.

## Project Structure

```
detent/
├── detent/                      # Main package
│   ├── __init__.py              # SDK exports (27 public APIs)
│   ├── schema.py                # AgentAction, ActionType, RiskLevel
│   ├── config.py                # DetentConfig, PipelineConfig, etc.
│   ├── cli.py                   # CLI commands (init, run, status, rollback)
│   ├── proxy/
│   │   ├── http_proxy.py        # HTTP reverse proxy (aiohttp)
│   │   ├── session.py           # Proxy session manager
│   │   └── types.py             # IPC message types
│   ├── adapters/                # Agent-specific adapters
│   │   ├── base.py              # AgentAdapter base class
│   │   ├── claude_code.py       # Claude Code PreToolUse hooks
│   │   └── langgraph.py         # LangGraph VerificationNode
│   ├── checkpoint/              # Atomic checkpoint/rollback
│   │   ├── engine.py            # CheckpointEngine class
│   │   └── savepoint.py         # SAVEPOINT and rollback logic
│   ├── pipeline/                # Verification pipeline
│   │   ├── pipeline.py          # VerificationPipeline orchestrator
│   │   └── result.py            # VerificationResult, Finding
│   ├── stages/                  # Verification stages
│   │   ├── base.py              # VerificationStage base class
│   │   ├── syntax.py            # tree-sitter syntax validation
│   │   ├── lint.py              # Ruff linting
│   │   ├── typecheck.py         # mypy type checking
│   │   └── tests.py             # pytest integration
│   ├── feedback/                # Feedback synthesis
│   │   └── synthesizer.py       # FeedbackSynthesizer class
│   └── ipc/                     # IPC control channel
│       └── channel.py           # Unix socket communication
│
├── tests/
│   ├── unit/                    # Fast tests (no external deps)
│   ├── integration/             # Full pipeline tests (with tools)
│   └── conftest.py              # Shared fixtures
│
├── Makefile                     # Development commands
├── pyproject.toml               # Dependencies and metadata
├── .editorconfig                # Editor settings
├── detent.yaml                  # Example configuration
└── README.md, CLAUDE.md, etc.   # Documentation
```

## Setup

### First Time Setup

```bash
# Clone the repository
git clone https://github.com/ofircohen205/detent.git
cd detent

# Install all dependencies (including dev extras and pre-commit hooks)
make install
# Or manually:
uv sync --all-extras --dev
uv run pre-commit install
```

### Using Make (Recommended)

```bash
# Install dependencies
make install

# Run all tests
make test

# Fast unit tests only
make test-unit

# Tests with coverage report
make test-cov

# Lint and format check
make check

# Auto-format code with ruff
make format

# Clean build artifacts
make clean
```

### Manual Commands

If you don't use Make:

```bash
# Install with uv
uv sync --all-extras --dev

# Run tests
uv run pytest tests/ -v

# Specific test file
uv run pytest tests/unit/test_pipeline.py -v

# Specific test
uv run pytest tests/unit/test_pipeline.py::test_sequential -v

# With coverage
uv run pytest tests/ --cov=detent --cov-report=term-missing

# Lint check
uv run ruff check detent/

# Type check
uv run mypy detent/

# Format check
uv run ruff format --check detent/

# Auto-format
uv run ruff format detent/
```

## Code Quality

Before pushing, make sure code passes all checks:

```bash
# All checks in one command
make check

# Or individually:
uv run ruff check detent/        # Lint
uv run ruff format detent/       # Format (in-place)
uv run mypy detent/              # Type check
uv run pytest tests/ -v          # Tests
```

> **Note:** The project uses `pre-commit` to automatically run Ruff and prevent commits directly to the `main` branch. This is installed automatically if you ran `make install` or `uv run pre-commit install`.

## Git Workflow

### Create a Feature Branch

```bash
# Update main
git checkout main
git pull

# Create feature branch
git checkout -b feature/my-feature

# Or use worktrees for isolation:
git worktree add .worktrees/my-feature -b feature/my-feature
cd .worktrees/my-feature
```

### Commit with Conventional Format

```bash
git commit -m "feat: add new verification stage"
git commit -m "fix: resolve bug in checkpoint engine"
git commit -m "docs: update README with examples"
git commit -m "test: add tests for feedback synthesizer"
```

### Push and Create PR

```bash
git push -u origin feature/my-feature

# Then create PR on GitHub
gh pr create --title "Add new feature" --body "Description..."
```

## Architecture Overview

### Two-Point Interception

```
Point 1: Conversation Layer
  AI Agent ──[LLM API]──> HTTP Proxy (DetentProxy)
  • Extract tool calls from LLM responses
  • Session state management

Point 2: Tool Execution Layer
  Agent ──[tool_call]──> Adapter ──> Checkpoint ──> Pipeline ──> Filesystem
  • Normalize to AgentAction
  • Create SAVEPOINT
  • Run verification
  • Rollback on failure
```

### Component Data Flow

```
AgentAction (normalized tool call)
    ↓
CheckpointEngine.savepoint(ref, files)
    ↓
VerificationPipeline.run(action)
    ├─ SyntaxStage
    ├─ LintStage
    ├─ TypecheckStage
    └─ TestsStage
    ↓
VerificationResult(passed=bool, findings=[Finding])
    ↓
FeedbackSynthesizer.synthesize(result, action)
    ↓
StructuredFeedback (JSON for agent)
    ↓
if not passed:
  CheckpointEngine.rollback(ref)
```

## Debug Mode

Enable detailed logging:

```bash
# Run with debug logging
DETENT_LOG_LEVEL=DEBUG detent run src/main.py

# Or in Python:
import logging
logging.basicConfig(level=logging.DEBUG)
```

**Log levels:**

- `DEBUG` — Detailed execution trace
- `INFO` — Key operations (stage start, decisions)
- `WARNING` — Issues (retries, recoveries)
- `ERROR` — Failures (stage errors, rollback failures)

## Running the Full Stack

Test everything together:

```bash
# Start HTTP proxy
detent proxy

# In another terminal, run agent
# Set: export ANTHROPIC_BASE_URL=http://localhost:7070
detent run src/file.py

# Or use docker-compose
docker-compose up
```

## Adding a Verification Stage

See [AGENTS.md](./AGENTS.md#adding-new-verification-stages) for detailed guide.

Quick steps:

1. Create `detent/stages/my_stage.py` implementing `VerificationStage`
2. Add your stage to `STAGE_REGISTRY` dict in `detent/stages/__init__.py`
3. Enable in `detent.yaml`
4. Write tests in `tests/unit/test_my_stage.py`
5. Test with `make test-unit`

## Adding an Agent Adapter

See [AGENTS.md](./AGENTS.md#adding-new-agent-adapters) for detailed guide.

Quick steps:

1. Create `detent/adapters/my_agent.py` implementing `AgentAdapter`
2. Register in `detent/adapters/__init__.py`
3. Write tests verifying normalization to `AgentAction`
4. Test with `make test`

## Testing Philosophy

### Unit Tests (Fast)

- Test each component in isolation
- Mock external dependencies
- Run in <1 second
- Located in `tests/unit/`

Example:

```python
def test_syntax_stage_detects_invalid_python(tmp_path):
    stage = SyntaxStage()
    bad_code = "def foo(  # missing closing paren"

    result = stage.run(action_with_content(bad_code, "broken.py"))

    assert not result.passed
    assert len(result.findings) > 0
    assert "syntax error" in result.findings[0].message.lower()
```

### Integration Tests (Slow)

- Test full pipeline with real tools
- Use real Python files
- Takes 5-10 seconds
- Located in `tests/integration/`

Example:

```python
async def test_full_pipeline_with_real_pytest(tmp_path):
    pipeline = VerificationPipeline.from_config(config)

    test_file = tmp_path / "test_example.py"
    test_file.write_text("""
def test_passes():
    assert 1 + 1 == 2
    """)

    action = AgentAction(file_path=str(test_file), ...)
    result = await pipeline.run(action)

    assert result.passed
    assert "tests" in [s.stage for s in result.metadata["stage_results"]]
```

## Performance Tips

- Use `make test-unit` during development (faster feedback)
- Use `make test-cov` before committing (verify coverage)
- Profile with `DETENT_LOG_LEVEL=DEBUG` if slow

## Troubleshooting Development

### "uv: command not found"

```bash
# Install uv if missing
pip install uv

# Or use official installer
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### "Tests failing after git pull"

```bash
# Clean and reinstall
make clean
make install
make test-unit
```

### "mypy import errors"

```bash
# Regenerate type stubs
uv sync --all-extras --dev

# Or manually
python -m mypy --install-types detent/
```

## Documentation

- **Code comments:** Explain _why_, not _what_
- **Docstrings:** All public classes/functions
- **Type hints:** Required for all functions
- **Examples:** Include in docstrings for complex APIs

Example docstring:

```python
async def run(self, action: AgentAction) -> VerificationResult:
    """Run verification pipeline on an agent action.

    Args:
        action: Normalized agent action to verify

    Returns:
        VerificationResult with findings and pass/fail status

    Raises:
        ValueError: If pipeline not properly configured

    Example:
        >>> pipeline = VerificationPipeline.from_config(config)
        >>> result = await pipeline.run(action)
        >>> if result.passed:
        ...     print("Verification succeeded!")
    """
```

## Resources

- [CLAUDE.md](./CLAUDE.md) — Claude Code-specific guidance
- [AGENTS.md](./AGENTS.md) — Detailed architecture and patterns
- [CONTRIBUTING.md](./CONTRIBUTING.md) — Contribution guidelines
- [SUPPORT.md](./SUPPORT.md) — FAQ and troubleshooting

Happy hacking! 🚀
