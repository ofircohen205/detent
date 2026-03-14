#!/usr/bin/env bash
set -euo pipefail

base_ref=""
if [[ -n "${DETENT_BASE_REF_INPUT:-}" ]]; then
  base_ref="$DETENT_BASE_REF_INPUT"
elif [[ "${GITHUB_EVENT_NAME:-}" == "pull_request" && -n "${DETENT_PR_BASE_SHA:-}" ]]; then
  base_ref="$DETENT_PR_BASE_SHA"
else
  base_ref="HEAD~1"
fi

files=$(git diff --name-only "$base_ref" HEAD -- || true)
filtered=""
while IFS= read -r file; do
  [[ -f "$file" ]] || continue
  filtered+="${file}"$'\n'
done <<< "$files"

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  {
    echo "files<<EOF"
    printf "%s" "$filtered"
    echo "EOF"
  } >> "$GITHUB_OUTPUT"
else
  printf "%s" "$filtered"
fi
