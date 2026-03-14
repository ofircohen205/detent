#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
SCRIPT="$ROOT_DIR/action/scripts/get-changed-files.sh"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

cd "$tmp_dir"
git init -q
git config user.email "ci@example.com"
git config user.name "CI"

mkdir -p src
echo "print('base')" > src/base.py
git add src/base.py
git commit -q -m "base"
base_ref="$(git rev-parse HEAD)"

echo "print('modified')" > src/base.py
echo "print('new')" > src/new.py
git add src/new.py
rm src/base.py
git add -u
git commit -q -m "change"

export DETENT_BASE_REF_INPUT="$base_ref"
export GITHUB_EVENT_NAME="push"
files="$("$SCRIPT")"

if echo "$files" | grep -q "src/base.py"; then
  echo "Deleted file should not be listed"
  exit 1
fi

if ! echo "$files" | grep -q "src/new.py"; then
  echo "New file should be listed"
  exit 1
fi

echo "ok"
