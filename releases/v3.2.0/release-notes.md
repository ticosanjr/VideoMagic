# VideoFlow 3.2.0

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- Deterministic overlay geometry: anchors, pixel margins, z-index, real
  collision detection, auto-packing, previews, and `layout.json`.
- Caption `effect` model with stable blocks, karaoke QA, and three-frame
  previews.
- Strict MP4 integrity gate, last-sentence guard, explicit mux duration, and a
  500 ms tail guard.
- `needs_review` status, granular progress/ETA, queued Shorts batches, and
  heartbeat renewal.
- Transcript dedupe, `shorts.tighten`, final QA with word fidelity, autofix,
  brand kits, and release kits.
- 32-tool core MCP surface.

## Artifacts

- `videoflow-3.2.0-linux-x86_64` — SHA-256 `d935a110e470ee544412c445b860b700e2fa909c90c78b5e3f7e759a01396976`
- `VideoFlow-3.2.0-x86_64.AppImage` — SHA-256 `f376c6d6210bd43c1260f91ea6d1688126d7b241f451af6a5f55a2253218fa0e`
- `VideoFlow-3.2.0-linux-x86_64.tar.zst` — SHA-256 `efb2788df6e8901bae51ac9d5b3d7219579bbfbd8740db9e966052bf4b33837d`
- `VideoFlow-3.2.0-mcp-servers.tar.zst` — SHA-256 `eb6dc1a646e4cc7b14788a5dd4089d52fa7828d90c700c2bac8d018216cba886`
- `sbom.json` — SHA-256 `b1520d9a093d0164ceccb04deb8ffd2bd57141558882a9488e76f24e9b3d0fd7`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.2.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.2.0-linux-x86_64 doctor
./videoflow-3.2.0-linux-x86_64 recipe list
./videoflow-3.2.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.2.0-x86_64.AppImage
./VideoFlow-3.2.0-x86_64.AppImage version
./VideoFlow-3.2.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
