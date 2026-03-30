# Installation Guide

Get Detent up and running in minutes.

## System Requirements

- **OS:** Linux or macOS (Windows is not supported)
- **Python:** 3.12 or later
- **Disk:** 500 MB for installation + dependencies
- **RAM:** 1 GB minimum (2+ GB recommended)

### Check Your Python Version

```bash
python3 --version
# Expected: Python 3.12.x or higher
```

If you don't have Python 3.12+, install it:

**macOS (using Homebrew):**

```bash
brew install python@3.12
```

**Ubuntu/Debian:**

```bash
sudo apt-get update
sudo apt-get install python3.12 python3.12-venv
```

**Fedora/RHEL:**

```bash
sudo dnf install python3.12
```

## Installation Methods

### Option 1: pip (Recommended for Users)

Install the latest release from PyPI:

```bash
pip install detent
```

Verify installation:

```bash
detent --version
# Expected: detent, version 1.2.0

detent --help
# Shows available commands
```

### Option 2: From Source (Development)

Clone the repository:

```bash
git clone https://github.com/ofircohen205/detent.git
cd detent
```

Install with all dependencies:

```bash
make install
# Or manually:
uv sync --all-extras
```

Verify:

```bash
uv run detent --version
```

Run tests to ensure everything works:

```bash
make test-unit
# Expected: all tests pass
```

### Option 3: Docker

Build the image:

```bash
docker build -t detent:latest .
```

Run as a container:

```bash
docker run -it \
  -v /path/to/project:/workspace \
  -p 7070:7070 \
  detent:latest \
  detent init
```

Or use docker-compose:

```bash
docker-compose up
```

## Initial Setup

Once installed, initialize Detent in your project:

```bash
cd my-project
detent init
```

**Interactive setup wizard will ask:**

1. **Agent type** — What agent are you using?
   - Auto-detected (Claude Code, LangGraph, etc.)
   - Manual selection if auto-detection fails

2. **Policy profile** — How strict should verification be?
   - `strict` — No findings allowed
   - `standard` — Allow warnings, block errors (default)
   - `permissive` — Log everything, allow all

3. **Execution mode** — How should stages run?
   - `sequential` — One at a time (default, safe)
   - `parallel` — Multiple at once (faster)

**Output:**

```
✅ Detent initialized!

Configuration saved to: detent.yaml
Session directory created: .detent/session/

Next steps:
1. Run: detent run src/main.py
2. View session: detent status
3. Learn more: detent run --help
```

## Verification

Test that everything is working:

### Test 1: Run a Python file

Create a test file:

```bash
cat > test_hello.py << 'EOF'
def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    print(hello("World"))
EOF
```

Run Detent on it:

```bash
detent run test_hello.py
```

**Expected output:**

```
✅ Syntax: PASS
✅ Lint (ruff): PASS
✅ Type check (mypy): PASS
✅ Tests (pytest): PASS

Verification passed!
Checkpoint: chk_before_write_000
```

### Test 2: Verify a failing file

Create a broken file:

```bash
cat > test_broken.py << 'EOF'
def broken(  # syntax error
    x)
    return x + "string"  # type error
EOF
```

Run Detent:

```bash
detent run test_broken.py
```

**Expected output shows failures:**

```
❌ Syntax: FAIL
  Unexpected closing parenthesis at line 1

Verification failed! Rolling back.
```

### Test 3: Check session state

```bash
detent status
```

**Expected output:**

```
Session ID: sess_abc123
Started: 2026-03-08 14:22:15 UTC
Checkpoints: 2
  ├─ chk_before_write_000 (test_hello.py) - restored
  └─ chk_before_write_001 (test_broken.py) - rolled_back
```

## Troubleshooting

### "detent command not found"

**Problem:** Installation succeeded but `detent` is not in PATH

**Solution:**

```bash
# If installed with pip:
which python3
# Then use full path:
$(which python3) -m detent --version

# Or add to ~/.bashrc or ~/.zshrc:
export PATH="$HOME/.local/bin:$PATH"
# Then reload: source ~/.bashrc
```

### "Python 3.12+ required"

**Problem:** `detent` requires Python 3.12 but you have an older version

**Solution:**

```bash
# Check available versions:
ls /usr/bin/python*

# Install newer Python:
# macOS: brew install python@3.12
# Ubuntu: sudo apt-get install python3.12

# Reinstall detent with specific Python:
python3.12 -m pip install detent
```

### "No module named 'detent'"

**Problem:** Python can't find the detent package

**Solution:**

```bash
# Verify installation:
pip show detent

# If not shown, reinstall:
pip install --upgrade --force-reinstall detent

# Check installation location:
pip install --verbose detent
```

### "Permission denied" on detent command

**Problem:** Installation created file without execute permission

**Solution:**

```bash
# Give execute permission:
chmod +x $(which detent)

# Or use python module directly:
python3 -m detent init
```

### "FileNotFoundError: detent.yaml"

**Problem:** You're in a directory without `detent.yaml`

**Solution:**

```bash
# Initialize Detent in this directory:
detent init

# Or specify the config file:
detent --config /path/to/detent.yaml run file.py
```

## Next Steps

1. **Learn the CLI:** `detent --help` or read [SUPPORT.md](./SUPPORT.md)
2. **Integration guide:** See [DEVELOPMENT.md](./DEVELOPMENT.md) for advanced setup
3. **Troubleshooting:** Check [SUPPORT.md](./SUPPORT.md) FAQ section
4. **API documentation:** See [AGENTS.md](./AGENTS.md) for SDK usage

## Getting Help

- **Questions?** → [GitHub Discussions](https://github.com/ofircohen205/detent/discussions)
- **Found a bug?** → [GitHub Issues](https://github.com/ofircohen205/detent/issues)
- **Security issue?** → [Create a Security Advisory](https://github.com/ofircohen205/detent/security/advisories/new)

---

Happy verifying! 🚀
