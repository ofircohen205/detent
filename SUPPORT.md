# Support & FAQ

## Getting Help

### For Questions & Ideas

Use **GitHub Discussions** — best for:

- How do I do X with Detent?
- Has anyone tried Y?
- Show & tell: here's what I built
- Feature ideas and brainstorming

→ [Start a discussion](https://github.com/ofircohen205/detent/discussions)

### For Bug Reports

Use **GitHub Issues** with tag `[BUG]` — best for:

- Something broke
- Unexpected behavior
- Error messages
- Environment details

→ [Report a bug](https://github.com/ofircohen205/detent/issues/new?template=bug_report.md)

### For Feature Requests

Use **GitHub Issues** with tag `[FEATURE]` — best for:

- I want Detent to do X
- This would solve my problem
- Alternative approaches

→ [Request a feature](https://github.com/ofircohen205/detent/issues/new?template=feature_request.md)

### For Security Issues

Use **GitHub Security Advisories** (never public GitHub issues)

See [SECURITY.md](./SECURITY.md) for full policy.

## FAQ

### Installation & Setup

**Q: I get "detent command not found" after installation**

A: The `detent` command isn't in your PATH. Try:

```bash
# Use full path to Python:
python3 -m detent --version

# Or add to ~/.bashrc:
export PATH="$HOME/.local/bin:$PATH"
source ~/.bashrc
```

See [INSTALLATION.md](./INSTALLATION.md#troubleshooting) for more.

**Q: Which Python version do I need?**

A: Python 3.12 or later. Check with:

```bash
python3 --version
```

**Q: Can I use Detent on Windows?**

A: No. Detent supports Linux and macOS only.

**Q: How do I uninstall Detent?**

A: Use pip:

```bash
pip uninstall detent
```

### Usage & Configuration

**Q: How do I initialize Detent in my project?**

A: Run the interactive setup:

```bash
cd my-project
detent init
```

This creates `detent.yaml` and `.detent/session/`.

**Q: What's the difference between policy profiles?**

A:

- `strict` — No issues allowed; fail on any finding
- `standard` — Allow warnings; fail on errors (default)
- `permissive` — Log everything; allow all writes

**Q: Can I customize verification stages?**

A: Yes! Edit `detent.yaml`:

```yaml
pipeline:
  stages:
    syntax: true # Enable syntax checking
    lint: true # Enable linting
    typecheck: true # Enable type checking
    tests: false # Disable test running
```

**Q: What does "parallel" execution do?**

A: Runs stages simultaneously instead of one-by-one:

```yaml
pipeline:
  mode: parallel # or "sequential" (default)
  workers: 4 # number of parallel workers
```

**Q: How do I see what Detent is doing?**

A: Enable debug logging:

```bash
DETENT_LOG_LEVEL=DEBUG detent run src/main.py
```

### Verification & Rollback

**Q: Why did my file fail verification?**

A: Run with debug logging to see detailed output:

```bash
DETENT_LOG_LEVEL=DEBUG detent run src/file.py
```

Check the findings for specific errors in:

- Syntax (parse errors)
- Lint (style/quality issues)
- Type checking (type errors)
- Tests (test failures)

**Q: Can I bypass verification in an emergency?**

A: Not recommended, but you can:

1. Edit `detent.yaml` and set `policy: permissive`
2. Or delete `.detent/` to disable sessions

Better: fix the issue and run verification again.

**Q: How do I rollback a change?**

A: View your checkpoints:

```bash
detent status
```

Then rollback:

```bash
detent rollback chk_before_write_001
```

**Q: How many checkpoints can I have?**

A: Unlimited. They're stored in `.detent/session/default.json`.

**Q: Can I manually edit checkpoints?**

A: Not recommended. The format is JSON but should be managed by Detent.

### Integration & Agents

**Q: Which agents does Detent support?**

A: Currently:

- ✅ Claude Code (production)
- ✅ LangGraph (tested)

Supported: Claude Code, Codex, Gemini (hook enforcement), LangGraph (VerificationNode)

**Q: How do I use Detent with Claude Code?**

A: Set the proxy as your Claude Code base URL:

```bash
export ANTHROPIC_BASE_URL=http://localhost:7070
```

Then start Detent proxy:

```bash
detent proxy
```

**Q: Does Detent work with LangGraph?**

A: Yes! Use `VerificationNode`:

```python
from detent.adapters.langgraph import VerificationNode

verification_node = VerificationNode(pipeline_config)
graph.add_node("verify", verification_node)
```

**Q: Can I use Detent programmatically?**

A: Yes! Import from the Python SDK:

```python
from detent import VerificationPipeline, AgentAction

pipeline = VerificationPipeline.from_config(config)
result = await pipeline.run(action)
```

See [AGENTS.md](./AGENTS.md) for API reference.

### Language Support

**Q: Does Detent support TypeScript/JavaScript?**

A: Not yet. v0.1 is Python-focused. TypeScript/JavaScript support is planned for v1.0.

**Q: Can I add a custom verification stage?**

A: Yes! See [DEVELOPMENT.md](./DEVELOPMENT.md#adding-a-verification-stage).

**Q: What about Go, Rust, Java?**

A: Coming in v1.0. See [ROADMAP.md](./ROADMAP.md) for timeline.

### Performance & Troubleshooting

**Q: Why is Detent slow?**

A: Common causes:

- Running all 4 stages (disable unnecessary ones in `detent.yaml`)
- Test execution (disable with `tests: false`)
- Large codebase (mypy type-checks everything)

Try:

```yaml
pipeline:
  mode: parallel
  stages:
    tests: false
```

**Q: Detent crashed! What do I do?**

A: Check logs:

```bash
DETENT_LOG_LEVEL=DEBUG detent run src/file.py 2>&1 | tee debug.log
```

Share the log in a [GitHub issue](https://github.com/ofircohen205/detent/issues).

**Q: I'm getting permission errors**

A: Detent needs write access to `.detent/` directory:

```bash
chmod -R 755 .detent/
```

Or in your project root:

```bash
ls -la | grep ".detent"
# Should show: drwxr-xr-x
```

**Q: How much disk space does Detent use?**

A: Shadow git repository stores checkpoints. Typical usage:

- Small projects (<100 files): < 50 MB
- Medium projects: 50-500 MB
- Large projects: 500 MB+

Clean up old sessions:

```bash
rm -rf .detent/session/
detent init  # Create new session
```

## Contributing Solutions

Found a solution to a problem? We'd love to hear it!

**Share:**

1. [GitHub Discussions](https://github.com/ofircohen205/detent/discussions) — General tips
2. [GitHub Issues](https://github.com/ofircohen205/detent/issues) — If it reveals a bug
3. [Pull Request](https://github.com/ofircohen205/detent/pulls) — If it's a documentation fix

## Still Stuck?

- Check [INSTALLATION.md](./INSTALLATION.md) troubleshooting section
- Read [DEVELOPMENT.md](./DEVELOPMENT.md) for technical deep dives
- Search [existing issues](https://github.com/ofircohen205/detent/issues)
- Start a [discussion](https://github.com/ofircohen205/detent/discussions)

We're here to help! 🚀
