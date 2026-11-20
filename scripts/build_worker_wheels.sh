#!/usr/bin/env bash
# Build the GPU worker and its portable rules dependency, then refresh the
# wheels shipped inside the Windows kit.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VERSION="${1:-$(uv run python -c 'from videoflow import __version__; print(__version__)')}"

uv build packages/scene-rules --out-dir dist
uv build packages/gpu-worker --out-dir dist

RULE_WHEEL="$(ls -t dist/videoflow_scene_rules-"${VERSION}"-*.whl | head -1)"
WORKER_WHEEL="$(ls -t dist/videoflow_gpu_worker-"${VERSION}"-*.whl | head -1)"
cp "$RULE_WHEEL" src/videoflow/templates/wheels/win/
cp "$WORKER_WHEEL" src/videoflow/templates/wheels/
rm -f src/videoflow/templates/wheels/videoflow_gpu_worker-"${VERSION}".old 2>/dev/null || true
printf '%s\n%s\n' "$RULE_WHEEL" "$WORKER_WHEEL"
