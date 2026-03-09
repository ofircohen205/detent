# Contributing to Detent

Thanks for your interest in contributing! This guide will help you get started.

## Code of Conduct

Please read [CODE_OF_CONDUCT.md](./CODE_OF_CONDUCT.md). We're committed to providing a welcoming and inspiring community for all.

## Ways to Contribute

### Report Bugs

Found something broken?
→ [Open a bug report](https://github.com/ofircohen205/detent/issues/new?template=bug_report.md)

Include:

- What broke (clear description)
- How to reproduce (steps)
- Expected vs actual behavior
- Environment (OS, Python version, Detent version)

### Request Features

Have an idea?
→ [Open a feature request](https://github.com/ofircohen205/detent/issues/new?template=feature_request.md)

Include:

- Problem it solves
- Proposed solution
- Alternatives considered

### Write Documentation

Docs unclear or missing?
→ [Open a documentation issue](https://github.com/ofircohen205/detent/issues/new?template=documentation.md)

Or submit a PR to fix it directly!

### Fix Bugs or Implement Features

Want to write code? Follow these steps:

## Development Setup

1. **Clone the repo:**

   ```bash
   git clone https://github.com/ofircohen205/detent.git
   cd detent
   ```

2. **Install dependencies:**

   ```bash
   make install
   # Or: uv sync --all-extras --dev
   ```

3. **Create a feature branch:**

   ```bash
   git checkout -b feature/my-feature
   # Or use worktrees for isolation:
   git worktree add .worktrees/my-feature -b feature/my-feature
   cd .worktrees/my-feature
   ```

4. **Run tests to verify setup:**
   ```bash
   make test-unit
   ```

For detailed setup, see [DEVELOPMENT.md](./DEVELOPMENT.md).

## Development Workflow

### 1. Write Tests First (TDD)

```python
# tests/unit/test_my_feature.py
def test_my_feature():
    result = my_function(input_value)
    assert result == expected_output
```

Run and verify it fails:

```bash
uv run pytest tests/unit/test_my_feature.py::test_my_feature -v
```

### 2. Implement Minimal Code

```python
# detent/my_module.py
def my_function(input_value):
    return expected_output
```

Run and verify test passes:

```bash
uv run pytest tests/unit/test_my_feature.py::test_my_feature -v
```

### 3. Run All Tests

```bash
make test-unit
# All tests should pass
```

### 4. Check Code Quality

```bash
make check
# Or individually:
uv run ruff check detent/
uv run ruff format detent/
uv run mypy detent/
```

Fix any issues:

```bash
uv run ruff format --fix detent/  # Auto-fix formatting
# Then manually fix lint and type issues
```

### 5. Commit

Use conventional commit messages:

```bash
git add detent/my_module.py tests/unit/test_my_feature.py
git commit -m "feat: add my new feature"
```

**Types:**

- `feat:` — New feature
- `fix:` — Bug fix
- `docs:` — Documentation changes
- `test:` — Test additions/fixes
- `chore:` — Maintenance, dependencies
- `refactor:` — Code restructuring (no behavior change)

Examples:

```bash
git commit -m "feat: add mypy verification stage"
git commit -m "fix: resolve checkpoint rollback race condition"
git commit -m "docs: update README with examples"
git commit -m "test: add edge case tests for pipeline"
```

### 6. Push and Create PR

```bash
git push -u origin feature/my-feature

# Then create PR on GitHub:
gh pr create --title "Short description" \
  --body "
Detailed description of changes.

Related issue: Fixes #123
"
```

## Pull Request Guidelines

Your PR should include:

- **What changed?** — Clear description
- **Why?** — Motivation and context
- **Testing plan** — How to verify
- **Breaking changes?** — Any API changes?
- **Checklist** — All boxes checked:
  - [ ] CI passing
  - [ ] Tests added
  - [ ] Docs updated
  - [ ] No debug statements

## Code Review

Your PR will be reviewed by maintainers for:

✅ **Correctness** — Does it work as intended?
✅ **Testing** — Are tests comprehensive?
✅ **Code quality** — Follows project standards?
✅ **Documentation** — Are changes documented?
✅ **Performance** — Any regressions?

**Response time:** 1-3 days typical (community-driven, best-effort)

Address feedback by:

1. Making requested changes
2. Pushing new commits (don't force-push)
3. Re-requesting review

## Testing Requirements

- **Unit tests** — Required for all features
- **Integration tests** — Required for pipeline/stage changes
- **Coverage** — Target >80% (check with `make test-cov`)
- **Real examples** — Test with actual tool output when possible

## Documentation

When adding features, also update:

- **Code comments** — Explain _why_, not _what_
- **Docstrings** — All public classes/functions
- **AGENTS.md** — If adding stage or adapter
- **DEVELOPMENT.md** — If adding new workflow
- **CHANGELOG.md** — Major features/fixes

## Adding a Verification Stage

See [DEVELOPMENT.md#adding-a-verification-stage](./DEVELOPMENT.md#adding-a-verification-stage).

Quick checklist:

- [ ] Create `detent/stages/my_stage.py`
- [ ] Implement `VerificationStage` interface
- [ ] Add to `STAGE_REGISTRY` dict in `detent/stages/__init__.py`
- [ ] Write unit tests (>80% coverage)
- [ ] Update AGENTS.md with stage docs
- [ ] Verify with `make test`

## Adding an Agent Adapter

See [DEVELOPMENT.md#adding-an-agent-adapter](./DEVELOPMENT.md#adding-an-agent-adapter).

Quick checklist:

- [ ] Create `detent/adapters/my_agent.py`
- [ ] Implement `AgentAdapter` interface
- [ ] Normalize tool calls to `AgentAction`
- [ ] Write tests for normalization
- [ ] Update AGENTS.md with adapter docs
- [ ] Verify with `make test`

## Commit Guidelines

### Branch Naming

- Feature: `feature/descriptive-name`
- Bug fix: `fix/issue-description`
- Docs: `docs/update-topic`

### Commit Message Format

```
<type>: <subject>

<body>

Fixes: #123
```

**Type:** feat, fix, docs, test, chore, refactor
**Subject:** Imperative, present tense, no period
**Body:** Explain what and why (optional)
**Issue:** Reference related issue

### Examples

```bash
git commit -m "feat: add mypy verification stage"

git commit -m "fix: resolve checkpoint rollback race condition

Ensure SAVEPOINT is created before pipeline runs.
Previously could lose data if pipeline crashed.

Fixes: #45"

git commit -m "docs: update README with installation steps"
```

## Before Submitting

Checklist:

```bash
# 1. All tests pass
make test

# 2. Code quality checks pass
make check

# 3. No commented code or print statements
grep -r "print(" detent/
grep -r "#.*TODO\|#.*FIXME\|#.*DEBUG" detent/

# 4. Commits are logical and well-messaged
git log --oneline -5

# 5. Branch is up to date with main
git pull origin main
```

## Questions?

- **How do I?** → [GitHub Discussions](https://github.com/ofircohen205/detent/discussions)
- **I found a bug** → [GitHub Issues](https://github.com/ofircohen205/detent/issues)
- **Security issue** → [Create a Security Advisory](https://github.com/ofircohen205/detent/security/advisories/new)
- **Something unclear?** → Open discussion or PR with clarification

---

Thank you for contributing to Detent! 🚀
