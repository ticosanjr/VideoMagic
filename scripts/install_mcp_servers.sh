#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
for package in vf-shared gpu-worker; do
  echo "==> $package"
  uv sync --project "$ROOT/packages/$package" --quiet
done
echo "VideoFlow environments ready."
