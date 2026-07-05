#!/bin/bash
set -euo pipefail

echo "=== Pipeline start: $(date -u) ==="

uv run python main.py

git add data/matrix
if ! git diff --cached --quiet; then
  git commit -m "Update ACH matrix output: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  git push origin master
else
  echo "No matrix changes to commit"
fi

echo "=== Pipeline complete: $(date -u) ==="
