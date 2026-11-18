# VideoFlow 3.1.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Stateful MCP: `vf_run` chains steps with full `PipelineContext` persistence,
  checkpoints, resume, and `through`.
- Unified SQLite job queue with `vf_jobs`, cross-process cancel, and real
  `wait=True`.
- Non-destructive timeline: source/timeline mapping, `keep_ranges`,
  `remove_ranges`, `dry_run`, force guard, history, undo, and restore.
- Normalized crop, crop preview, corrected ASS wrapping/tags/dedup, intro
  caption offset, and mandatory font directory.
- 100 ms MP4 duration gate, CFR repair, one export engine for video/bundle/NLE,
  and PCM 24-bit delivery sidecars.
- Cached rounded masks, hard-cut macro-blocks, filter scripts, analysis cache,
  hardlinked media pool, and disk preflight/prune.
- Style validation/compiler, beat-map plans, overlays, Shorts batch, final MP4
  QA, and font management.
- Core MCP surface now has 28 tools; recipes remain UI/CLI/REST-only.

## Artifacts

- `videoflow-3.1.0-linux-x86_64` — SHA-256 `c3a924238dec14997013213ac5ca07f363f12ae7ce53d9c123656ede98cb1139`
- `VideoFlow-3.1.0-x86_64.AppImage` — SHA-256 `4557b789e0be13b78819a98085aba56dfc2ec9b8c1d34a2b27d556f79d727e85`
- `VideoFlow-3.1.0-linux-x86_64.tar.zst` — SHA-256 `44f300053b84bf98ddfe8bae3ad8cdf1eac6107afb88d19a7d5641375665ce34`
- `VideoFlow-3.1.0-mcp-servers.tar.zst` — SHA-256 `0943d144389971ba1f933d5a28e7fe039b8f16280ec463ce1f17dccb8e733cff`
- `sbom.json` — SHA-256 `146dbba9658ea9f5ffaf7fc24f031bdde74162d8eaf7e75845e66e7f03d45acc`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.1.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.1.0-linux-x86_64 doctor
./videoflow-3.1.0-linux-x86_64 recipe list
./videoflow-3.1.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.1.0-x86_64.AppImage
./VideoFlow-3.1.0-x86_64.AppImage version
./VideoFlow-3.1.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
