#!/usr/bin/env bash
# One local gate: static checks, Python, media, UI, E2E, coverage, residuals.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "== ruff =="
uv run ruff check src tests scripts

echo "== python unit/contract (coverage gate) =="
uv run pytest tests/unit tests/contract -q --no-header

echo "== fault injection =="
uv run pytest tests/unit/test_hardening.py tests/unit/test_queue_claim.py -q --no-header --no-cov

echo "== media =="
uv run pytest tests -q --no-header --no-cov -m media

echo "== coverage by layer =="
cat > /tmp/videoflow-coverage.rc <<'RC'
[run]
branch = True
source = videoflow

[report]
show_missing = True
RC
uv run coverage run --rcfile=/tmp/videoflow-coverage.rc -m pytest tests/unit tests/contract -q -o addopts="" >/tmp/videoflow-coverage.log
uv run python scripts/coverage_layers.py

echo "== UI unit/static =="
(
  cd ui
  npm test -- --reporter=basic
  npx svelte-check --tsconfig ./tsconfig.json
  npm run build
  npx playwright test --reporter=line
  VF_PERF=1 npx playwright test e2e/perf.spec.ts --workers=1 --reporter=line
)

echo "gate: all local checks passed"
