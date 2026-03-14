#!/usr/bin/env bash
set -euo pipefail

DETENT_CONFIG="${DETENT_CONFIG:-detent.yaml}"
FILES="${DETENT_FILES:-}"

if [[ -z "$FILES" ]]; then
  echo "No changed files to check."
  exit 0
fi

SUMMARY_FILE="${GITHUB_STEP_SUMMARY:-}"
if [[ -z "$SUMMARY_FILE" ]]; then
  SUMMARY_FILE="$(mktemp)"
fi

{
  echo "| File | Severity | Line | Message |"
  echo "| --- | --- | --- | --- |"
} >> "$SUMMARY_FILE"

FINDINGS=0
ERRORS=0

while IFS= read -r file; do
  [[ -f "$file" ]] || continue

  output="$(DETENT_CONFIG="$DETENT_CONFIG" detent run "$file" --json 2>&1 || true)"
  count_file="$(mktemp)"
  python - "$file" "$count_file" "$SUMMARY_FILE" <<'PY' <<< "$output"
import json
import os
import sys

file_path = sys.argv[1]
count_path = sys.argv[2]
summary_path = sys.argv[3]
raw = sys.stdin.read()

def emit_annotation(level, message, line=None, col=None):
    parts = [f"::{level}"]
    if file_path:
        location = f"file={file_path}"
        if line:
            location += f",line={line}"
        if col:
            location += f",col={col}"
        parts.append(f"{location}::")
    else:
        parts.append("::")
    print("".join(parts) + message)

def write_counts(findings, errors):
    with open(count_path, "w", encoding="utf-8") as fh:
        fh.write(f"{findings} {errors}")

try:
    result = json.loads(raw)
except json.JSONDecodeError:
    emit_annotation("error", f"Detent internal error for {file_path}: {raw.strip()}")
    write_counts(0, 1)
    sys.exit(0)

if result.get("error"):
    emit_annotation("error", f"Detent error for {file_path}: {result['error']}")
    write_counts(0, 1)
    sys.exit(0)

findings = result.get("findings", [])
errors = 0
for finding in findings:
    severity = finding.get("severity", "warning")
    level = "warning"
    if severity == "error":
        level = "error"
        errors += 1
    elif severity == "info":
        level = "notice"
    line = finding.get("line")
    col = finding.get("column")
    message = f"{finding.get('message', '')} [{finding.get('stage', 'unknown')}/{finding.get('code', '')}]"
    emit_annotation(level, message, line=line, col=col)
    with open(summary_path, "a", encoding="utf-8") as fh:
        fh.write(f"| {finding.get('file', file_path)} | {severity} | {line or ''} | {finding.get('message', '')} |\n")

if result.get("rollback_failed"):
    emit_annotation("error", f"Rollback failed for {file_path}")
    errors += 1

write_counts(len(findings), errors)
PY

  read -r file_findings file_errors < "$count_file"
  rm -f "$count_file"

  FINDINGS=$((FINDINGS + file_findings))
  ERRORS=$((ERRORS + file_errors))
done <<< "$FILES"

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  echo "findings-count=$FINDINGS" >> "$GITHUB_OUTPUT"
  echo "errors-count=$ERRORS" >> "$GITHUB_OUTPUT"
fi

if [[ "$ERRORS" -gt 0 ]]; then
  exit 1
fi
