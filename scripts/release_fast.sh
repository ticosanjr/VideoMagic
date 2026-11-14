#!/usr/bin/env bash
# Fast local release: source overlay on a prebuilt onedir runtime + tar.zst.
# Use --full for the complete onefile + AppImage release with the full gate.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ "${1:-}" = "--full" ]; then
  shift
  exec "$ROOT/scripts/release_local.sh" "$@"
fi

REFRESH_RUNTIME="${VIDEOWFLOW_REFRESH_RUNTIME:-0}"
CLEAN_FLAG="--no-clean"
if [ "${1:-}" = "--refresh-runtime" ]; then
  REFRESH_RUNTIME=1
  shift
fi
if [ "${1:-}" = "--clean" ]; then
  CLEAN_FLAG="--clean"
  REFRESH_RUNTIME=1
  shift
fi

VERSION="${1:-$(uv run python -c 'from videoflow import __version__; print(__version__)')}"
RUNTIME_BASE="$ROOT/build/videoflow-base"

TOTAL_START=$(date +%s)
STEP_START=$TOTAL_START
mark() {
  local now
  now=$(date +%s)
  printf '  %-24s %3ss\n' "$1" "$((now - STEP_START))"
  STEP_START=$now
}

echo "Fast release ${VERSION}"

uv run python scripts/bump_version.py "$VERSION"
mark "version"

"$ROOT/scripts/gate_local.sh" --fast
mark "fast gate"

(
  cd ui
  npm run build
)
mark "UI build"

if [ "$REFRESH_RUNTIME" = "1" ] || [ ! -x "$RUNTIME_BASE/videoflow" ]; then
  WHISPER_VULKAN=()
  if command -v glslc >/dev/null 2>&1; then
    WHISPER_VULKAN=(--whisper-vulkan)
  fi
  uv run python scripts/build_portable.py \
    --onedir \
    --skip-ui-build \
    "$CLEAN_FLAG" \
    --with-ffmpeg \
    --with-whisper \
    "${WHISPER_VULKAN[@]}" \
    --with-silero \
    --with-faster-whisper \
    --runtime-base "$RUNTIME_BASE"
  mark "runtime base"
else
  echo "reusing runtime base: $RUNTIME_BASE"
  mark "runtime base"
fi

rm -rf dist/videoflow
cp -al "$RUNTIME_BASE" dist/videoflow
mkdir -p dist/videoflow/app/videoflow
rsync -a --delete --exclude='__pycache__' \
  "$ROOT/src/videoflow/" "$ROOT/dist/videoflow/app/videoflow/"
printf '%s\n' "$VERSION" > dist/videoflow/app/version.txt
rm -rf dist/videoflow/ui
cp -a "$ROOT/ui/build" dist/videoflow/ui
mark "bundle"

./dist/videoflow/videoflow version
mark "smoke"

ARCHIVE="dist/VideoFlow-${VERSION}-linux-x86_64.tar.zst"
rm -f "$ARCHIVE"
tar -C dist -I 'zstd -1 -T0' -cf "$ARCHIVE" videoflow
mark "tar.zst"

uv run python scripts/generate_sbom.py --output dist/sbom.json
uv run python scripts/release.py \
  --version "$VERSION" \
  --force \
  --keep 3 \
  --no-defaults \
  --artifact "$ARCHIVE" \
  --artifact dist/sbom.json
mark "stage"

(
  cd "releases/v${VERSION}"
  sha256sum -c SHA256SUMS
)
mark "checksums"

echo
echo "Fast release staged in releases/v${VERSION}"
echo "Total: $(( $(date +%s) - TOTAL_START ))s"
echo "Artifacts are local only. Nothing was pushed or published."
