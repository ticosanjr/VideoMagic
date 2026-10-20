# Releases

Every release gets a versioned folder:

```
releases/v0.4.0/
  videoflow-linux-x86_64    # local artifact, ignored by git
  SHA256SUMS                # tracked
  manifest.json             # tracked
  release-notes.md          # tracked
```

## Policy

1. Stage the artifact with `uv run python scripts/release.py --version X.Y.Z`.
2. Verify `doctor`, `demo`, and the three exports on the staged binary.
3. Commit the notes, checksums, and manifest. The binary is ignored because
   GitHub rejects files over 100 MB in normal git history.
4. Upload the binary as a GitHub Release asset:

```bash
gh release create vX.Y.Z releases/vX.Y.Z/<asset> \
  --title "VideoFlow X.Y.Z" \
  --notes-file releases/vX.Y.Z/release-notes.md
```

All artifacts are built locally; GitHub Actions is not used.

```bash
uv run python scripts/build_portable.py --fetch-ffmpeg
uv run python scripts/build_appimage.py
# Windows PE via Wine + embeddable Python, see docs/manuals/portable.md
uv run python scripts/release.py
```

Upload the staged assets manually:

```bash
gh release create vX.Y.Z releases/vX.Y.Z/* \
  --title "VideoFlow X.Y.Z" \
  --notes-file releases/vX.Y.Z/release-notes.md
```

A release is not complete until the Linux binary, AppImage, and Windows `.exe`
exist and their checksums are recorded here.

## Current

- `v0.8.0`: Linux binary, AppImage, and Windows PE. Local builds, no CI.
- `v0.7.0`: Linux x86_64, static FFmpeg. Artifact downloads and UI presets.
- `v0.6.0`: Linux x86_64, static FFmpeg. SRT retakes and LLM guard.
- `v0.5.0`: Linux x86_64, static FFmpeg. UI drives real jobs. Windows pending CI.
- `v0.4.0`: Linux x86_64, static FFmpeg, 168 MB. Windows pending CI.
