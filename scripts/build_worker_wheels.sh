#!/usr/bin/env bash
# Build the GPU worker and its portable rules dependency, then refresh the
# wheels shipped inside the Windows kit.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
VERSION="${1:-$(uv run python -c 'from videoflow import __version__; print(__version__)')}"

uv build packages/vf-shared --out-dir dist
uv build packages/gpu-worker --out-dir dist

SHARED_WHEEL="$(ls -t dist/vf_shared-"${VERSION}"-*.whl | head -1)"
WORKER_WHEEL="$(ls -t dist/videoflow_gpu_worker-"${VERSION}"-*.whl | head -1)"
cp "$SHARED_WHEEL" src/videoflow/templates/wheels/win/
cp "$WORKER_WHEEL" src/videoflow/templates/wheels/
rm -f src/videoflow/templates/wheels/videoflow_gpu_worker-"${VERSION}".old 2>/dev/null || true
printf '%s\n%s\n' "$SHARED_WHEEL" "$WORKER_WHEEL"
