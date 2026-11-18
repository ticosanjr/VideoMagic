# VideoFlow 3.2.1

Portable video pre-edit pipeline with offline whisper.cpp transcription.

## Highlights

- New cinematic/retention styles:
  `lf-depth-title-cinema`, `lf-3d-web-showcase`, `lf-parallax-25d-doc`, and
  `sr-depth-3d-viral`, synced to `presets/` and shipped in the central catalog.
- `AGENTS.md` and the OpenCode bootstrap template now document depth
  compositing, 3D web showcase, Ken Burns, and parallax 2.5D recipes.
- NLE overlay transforms and z-order lanes for FCPXML, XMEML, and Kdenlive.
- Automatic `layout.json` beside every MP4 deliverable.
- Final QA, autofix rerender, caption effect fallback, Short tightening and
  crossfades, curation previews, and channel brand kits.
- 32-tool MCP surface.

## Artifacts

- `videoflow-3.2.1-linux-x86_64` — SHA-256 `9d32f6e39d4cd1ec5d5a3c472ab582390c0afb7b66ffbd1e7d84571319554124`
- `VideoFlow-3.2.1-x86_64.AppImage` — SHA-256 `35a367c89633002874f8e15f3d5938e4c09026e915fbf200973595c3fccdbc3e`
- `VideoFlow-3.2.1-linux-x86_64.tar.zst` — SHA-256 `9f70b270d5d331ebc73db28ede770865b0fbf0ea1a33535db40d6521ccd7c15a`
- `VideoFlow-3.2.1-mcp-servers.tar.zst` — SHA-256 `0dab51439cf8560e7e7b8494084c31023ec3538c39f9d34690ddbd4ea29cf16e`
- `sbom.json` — SHA-256 `e42af808c435b8d2875639106c16f7f7f872f9627ef10d9de4b08e546f6a1a41`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.2.1-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.2.1-linux-x86_64 doctor
./videoflow-3.2.1-linux-x86_64 recipe list
./videoflow-3.2.1-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.2.1-x86_64.AppImage
./VideoFlow-3.2.1-x86_64.AppImage version
./VideoFlow-3.2.1-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
