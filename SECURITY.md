# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in Detent, please report it responsibly by creating a private **GitHub Security Advisory** in this repository instead of opening a public GitHub issue.

### What to Include

Include the following information:

1. **Description** — What is the vulnerability? (be specific)
2. **Severity** — How critical is it? (critical/high/medium/low)
3. **Reproduction steps** — How to trigger the vulnerability
4. **Impact** — What could an attacker do?
5. **Suggested fix** — If you have one (optional)
6. **Environment** — OS, Python version, Detent version

### Example Report

```
Subject: [SECURITY] SQL injection in checkpoint query

Description:
The checkpoint engine uses unsanitized file paths in shadow git queries,
allowing attackers to craft malicious filenames that execute arbitrary git commands.

Severity: High

Reproduction:
1. Create file with name: "file.py; rm -rf /"
2. Run: detent run "file.py; rm -rf /"
3. Shadow git executes arbitrary command

Impact:
Arbitrary code execution on the machine running Detent.

Suggested fix:
Escape file paths using shlex.quote() before passing to git subprocess.
```

## Response Timeline

- **Acknowledgment**: Within 48 hours
- **Assessment**: Within 1 week
- **Fix**: Critical (24-48 hours), High (1 week), Medium (2 weeks), Low (next release)
- **Disclosure**: After patch is released

## Security Policy

1. **No public disclosure** until patch is available
2. **No social engineering** — Stick to technical details
3. **No access attempts** — Don't try to exploit other systems
4. **Good faith** — We assume you're reporting in good faith

## Vulnerability Disclosure

Once a patch is released:

1. We'll announce the vulnerability in CHANGELOG.md
2. You may publish your findings (optional)
3. You'll be credited as discoverer (if desired)

## Out of Scope

The following are **not** security vulnerabilities:

- Missing documentation
- Configuration mistakes
- Denial of service (running out of disk space)
- Social engineering / phishing
- Issues in dependencies (report to maintainer directly)

## Contact

**Report**: Create a [GitHub Security Advisory](https://github.com/ofircohen205/detent/security/advisories/new)
**PGP**: Available upon request

---

Thank you for helping keep Detent secure!
