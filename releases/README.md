# Releases

Every release gets a versioned folder:

```
releases/v0.21.2/
  videoflow-0.21.2-linux-x86_64    # local artifact, ignored by git
  VideoFlow-0.21.2-x86_64.AppImage # local artifact, ignored by git
  videoflow-0.21.2-windows-x86_64.exe
  SHA256SUMS                       # tracked
  manifest.json                    # tracked
  release-notes.md                 # tracked
```

## Policy

1. Stage the artifacts with `uv run python scripts/release.py --version X.Y.Z`.
2. Verify `version`, `doctor`, `demo`, and the three exports on each artifact.
3. Commit the notes, checksums, and manifest. Binaries are ignored because
   GitHub rejects files over 100 MB in normal git history.
4. Keep the binaries in this folder. GitHub Actions is not used for this
   project. Upload the binaries as GitHub Release assets after the board
   authorizes the release; only checksums, manifests, and notes are committed.
5. Keep at most **three** `v*` folders. `scripts/release.py` prunes older ones
   automatically; `--keep N` changes the retention count. Historical notes stay
   in `CHANGELOG.md` and git history.
6. After staging, remove `build/`, `dist/`, coverage files, and generated
   caches. The version folder is the canonical artifact store.

```bash
uv run python scripts/build_portable.py --fetch-ffmpeg --with-whisper \
  --with-silero --with-faster-whisper
uv run python scripts/build_appimage.py
# Optional fully offline build: add --with-models
# Windows PE via Wine + embeddable Python, see docs/manuals/portable.md
uv run python scripts/release.py --version X.Y.Z --keep 3
```

`--require-all` fails unless the Linux binary, AppImage, and Windows `.exe` are
present. Every asset name includes the version, for example:

```
videoflow-0.21.2-linux-x86_64
VideoFlow-0.21.2-x86_64.AppImage
videoflow-0.21.2-windows-x86_64.exe
```

## Current

- `v0.22.2`: version-aware replacement of old services, Services control tab,
  process cleanup, and server logs.
- `v0.22.1`: file-browser 500 fix, persistent service lifecycle, Restart/Stop
  controls, `status`/`stop`/`restart` commands, and single-instance reopen.
- `v0.22.0`: LLM vision Studio, LLM emoji captions, on-demand model downloads,
  lean builds without weight files, 30 language codes, and 1080/1440/2160
  short-edge renders. Linux binary and AppImage uploaded as GitHub assets.
- `v0.21.2`: FCPXML/Resolve audio fade keyframes, DTD-valid sequence audio
  rates, and a live 9:16 caption preview in the Shorts card.
- `v0.21.1`: Premiere xmeml audio `transitionitem` fades and Kdenlive keyframed
  `volume` fades. Linux binary, AppImage, and Windows PE built and smoke-tested.
- `v0.21.0`: configurable zoom bounds, audio fades, Shorts target/minimum and
  selection strategy, `run --shorts`, and full caption/karaoke styling across
  UI, API, project config, presets, and MCP. Linux binary, AppImage, and Windows
  PE built and smoke-tested.

Older release folders are intentionally pruned. Their notes remain in
`CHANGELOG.md` and the tagged git history.
