# Releases

Every release gets a versioned folder:

```
releases/v0.4.0/
  videoflow-0.4.0-linux-x86_64    # local artifact, ignored by git
  SHA256SUMS                      # tracked
  manifest.json                   # tracked
  release-notes.md                # tracked
```

## Policy

1. Stage the artifacts with `uv run python scripts/release.py --version X.Y.Z`.
2. Verify `version`, `doctor`, `demo`, and the three exports on each artifact.
3. Commit the notes, checksums, and manifest. Binaries are ignored because
   GitHub rejects files over 100 MB in normal git history.
4. Keep the binaries in this folder. GitHub Actions is not used for this
   project. Uploading to a GitHub Release is a separate, manual decision.

```bash
uv run python scripts/build_portable.py --fetch-ffmpeg
uv run python scripts/build_appimage.py
# Windows PE via Wine + embeddable Python, see docs/manuals/portable.md
uv run python scripts/release.py
```

A release is not complete until the Linux binary, AppImage, and Windows `.exe`
exist in the version folder and their checksums are recorded here. Every asset
name includes the version, for example:

```
videoflow-0.9.0-linux-x86_64
VideoFlow-0.9.0-x86_64.AppImage
videoflow-0.9.0-windows-x86_64.exe
```

## Current

- `v0.11.0`: per-block telemetry, logs drawer, configurable rack, new UI.
- `v0.10.0`: vertical shorts engine (1080x1920, ASS captions), versioned assets.
- `v0.9.1`: AppImage starts the UI when opened with no arguments; AppImage
  contract tests.
- `v0.9.0`: Linux binary, AppImage, and Windows PE; transcript/cull API and UI
  inspector. Versioned asset names.
- `v0.8.0`: Linux binary, AppImage, and Windows PE. Local builds, no CI.
- `v0.7.0`: Linux x86_64, static FFmpeg. Artifact downloads and UI presets.
- `v0.6.0`: Linux x86_64, static FFmpeg. SRT retakes and LLM guard.
- `v0.5.0`: Linux x86_64, static FFmpeg. UI drives real jobs. Windows pending CI.
- `v0.4.0`: Linux x86_64, static FFmpeg, 168 MB. Windows pending CI.
