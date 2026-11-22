#!/usr/bin/env bash
# Build and stage the Linux portable binary, AppImage, SBOM, and checksums.
# This does not use GitHub Actions and does not publish anything.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

CLEAN_FLAG="--no-clean"
VERSION=""
for arg in "$@"; do
  case "$arg" in
    --clean)
      CLEAN_FLAG="--clean"
      ;;
    --no-clean)
      CLEAN_FLAG="--no-clean"
      ;;
    *)
      VERSION="$arg"
      ;;
  esac
done
VERSION="${VERSION:-$(uv run python -c 'from videoflow import __version__; print(__version__)')}"

echo "Building VideoFlow ${VERSION} locally"
echo "PyInstaller cache: ${CLEAN_FLAG#--}"
(
  cd ui
  npm run build
)

WHISPER_VULKAN=()
if command -v glslc >/dev/null 2>&1; then
  WHISPER_VULKAN=(--whisper-vulkan)
fi

uv run python scripts/build_portable.py \
  --with-ffmpeg \
  --with-whisper \
  "${WHISPER_VULKAN[@]}" \
  --with-silero \
  --with-faster-whisper \
  --with-tray \
  --skip-ui-build \
  "$CLEAN_FLAG"

# Build an onedir runtime for the AppImage. The onefile payload extracts on
# every launch, which makes the MCP server slow enough to hit OpenCode's
# startup timeout. The onedir AppImage mounts once and starts immediately.
uv run python scripts/build_portable.py \
  --onedir \
  --name videoflow-appimage \
  --with-ffmpeg \
  --with-whisper \
  "${WHISPER_VULKAN[@]}" \
  --with-silero \
  --with-faster-whisper \
  --with-tray \
  --skip-ui-build \
  "$CLEAN_FLAG"

uv run python scripts/build_appimage.py --onedir dist/videoflow-appimage
uv run python scripts/generate_sbom.py --output dist/sbom.json
uv run python scripts/release.py --version "$VERSION" --force --keep 3

echo
echo "Staged releases/v${VERSION}:"
ls -lh "releases/v${VERSION}"
echo
echo "Artifacts are local only. Nothing was pushed or published."
