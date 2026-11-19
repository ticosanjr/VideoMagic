#!/usr/bin/env bash
# Local checks with a fast default and a full on-demand mode.
#
#   ./scripts/gate_local.sh          # fast: ruff, changed Python tests, UI unit
#   ./scripts/gate_local.sh --full   # full: media, coverage, E2E, perf
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MODE="${1:---fast}"
case "$MODE" in
  fast | --fast) MODE=fast ;;
  full | --full) MODE=full ;;
  *)
    echo "usage: $0 [--fast|--full]" >&2
    exit 2
    ;;
esac

echo "== ruff =="
uv run ruff check src tests scripts

if [ "$MODE" = "fast" ]; then
  echo "== changed Python tests =="
  mapfile -t TEST_FILES < <(uv run python scripts/changed_tests.py)
  if [ "${#TEST_FILES[@]}" -gt 0 ]; then
    printf '  %s\n' "${TEST_FILES[@]}"
    uv run pytest "${TEST_FILES[@]}" -q --no-header -o addopts=""
  else
    echo "  no Python changes; skipping pytest"
  fi

  echo "== UI unit/static =="
  (
    cd ui
    npm test -- --reporter=dot
    npx svelte-check --tsconfig ./tsconfig.json
  )

  echo "gate: fast checks passed"
  exit 0
fi

echo "== fault injection =="
uv run pytest tests/unit/test_hardening.py tests/unit/test_queue_claim.py -q --no-header --no-cov

echo "== media =="
uv run pytest tests -q --no-header --no-cov -m media

echo "== full coverage (single run) =="
cat > /tmp/videoflow-coverage.rc <<'RC'
[run]
branch = True
source = videoflow
omit =
    */application/audio_compare.py
    */application/reference_edl.py

[report]
show_missing = True
RC
uv run coverage run --rcfile=/tmp/videoflow-coverage.rc -m pytest tests/unit tests/contract -q -o addopts="" >/tmp/videoflow-coverage.log
uv run coverage report \
  --rcfile=/tmp/videoflow-coverage.rc \
  --include='src/videoflow/domain/*,src/videoflow/application/cache.py,src/videoflow/application/timeline_builder.py' \
  --fail-under=95
uv run python scripts/coverage_layers.py

echo "== UI unit/static/build =="
(
  cd ui
  npm test -- --reporter=dot
  npx svelte-check --tsconfig ./tsconfig.json
  npm run build
)

echo "== E2E =="
(
  cd ui
  npx playwright test --reporter=line
)

echo "gate: all local checks passed"
