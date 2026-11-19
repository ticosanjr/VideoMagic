# VideoFlow 3.6.0

Portable video pre-edit pipeline controlled through MCP.

## Highlights

- **MCP-first cleanup.** The local UI is now a control panel for jobs and setup
  only. The recipe studio, canvas timeline, Lamera workspace, assistant,
  schedules, media library, brand/publish screens, and their tests were removed.
- Removed the REST routes that only served those screens: recipes, batches,
  copilot, library, media, presets, publishing, schedules, styles, timeline,
  workflows, discovery extras, and assets.
- Removed the copilot, assistant, and schedule application modules. The MCP
  runtime no longer depends on `BatchManager`; unused legacy helpers
  `vf_wait_job` and `vf_get_transcript` were removed.
- `./scripts/gate_mcp.sh` now enforces **80% coverage** on
  `src/videoflow/mcp_server` (current: 85%).
- 33 MCP tools, media contract, `audio.finalize`, HTTP-first GPU transport,
  multi-source ingest, immutable QA reports, and the self-healing Windows kit
  remain available.

## Known limitations

- Physical ASR/NVENC/matte speed certification on Windows/NVIDIA hardware is
  still pending. No speedup is claimed without a real RTX 3060 run. See
  `docs/qa-evidence/3.6.0-gpu.json`.
- The Linux artifacts are not code-signed.

## Artifacts

- `videoflow-3.6.0-linux-x86_64` — SHA-256 `7acc41ba46e8fb3b47a241ee31224aefe72a27ab47b09253703c9b2b68c73dd6`
- `VideoFlow-3.6.0-x86_64.AppImage` — SHA-256 `f85a6c08b6f77de0afd5f2bc92109c93c87ae217d4a6dc090b2d16a474f0e8cb`
- `sbom.json` — SHA-256 `8b737f9e8640fc13a506df527ad184a923374dd847f43d59da777e7841355045`
- `VideoFlow-3.6.0-linux-x86_64.tar.zst` — SHA-256 `ee9ee68d7a03f012d85f95310c2bb50dd846a284ab0d424fca152c7ba48af289`
- `VideoFlow-3.6.0-mcp-servers.tar.zst` — SHA-256 `e2056657ccfe9108da4d5c8be3b0d1e7209abffb2f61c13e0e10e76db087ce5f`

## Run

Linux portable bundle:

```bash
tar --zstd -xf VideoFlow-3.6.0-linux-x86_64.tar.zst
./videoflow/videoflow doctor
./videoflow/videoflow recipe list
./videoflow/videoflow serve --open
```

Linux plain binary:

```bash
./videoflow-3.6.0-linux-x86_64 doctor
./videoflow-3.6.0-linux-x86_64 recipe list
./videoflow-3.6.0-linux-x86_64 recipe run youtube_talking_head input.mp4 -o project
```

Linux AppImage (no FUSE required with extract-and-run):

```bash
chmod +x VideoFlow-3.6.0-x86_64.AppImage
./VideoFlow-3.6.0-x86_64.AppImage version
./VideoFlow-3.6.0-x86_64.AppImage recipe list
```

## Notes

See `CHANGELOG.md`.
