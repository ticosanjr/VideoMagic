# VideoFlow 3.12.0

Short render cache and upload deduplication.

## Artifacts

- `videoflow-3.12.0-linux-x86_64`
- `VideoFlow-3.12.0-x86_64.AppImage`
- `VideoFlow-3.12.0-linux-x86_64.tar.zst`
- `VideoFlow-Windows-GPU-Worker-3.12.0.zip`
- `sbom.json`, `SHA256SUMS`, `manifest.json`

## Performance

- Persistent Short segment cache keyed by source fingerprint, crop, filter,
  FPS, and encoder. Rerenders skip micro-clips and only rebuild changed pieces.
- Worker reuse of the same segment cache under `short_segment_cache`.
- Upload init returns existing content-addressed artifacts, avoiding duplicate
  uploads of identical source files.
- All prior worker lanes, NVENC tuning, hardlinks, metrics, dashboard, and
  public Windows kit remain.

## Verification

- MCP: 424 passed, 84% coverage, 35 tools, 16 resources.
- Python non-media: 2,839 passed, 1 skipped, 1 xfailed.
- Media: 29 passed, 2 skipped.
- UI: 52 Vitest, svelte-check 0, build OK.
- AppImage/onefile report `videoflow 3.12.0 (linux-x86_64)`.
- Public Windows kit is tokenless and includes worker wheel + dashboard.

## Pending

Physical RTX 3060 NVENC certification still requires the Windows machine.
The acceptance harness and blocked evidence are in the repository.
