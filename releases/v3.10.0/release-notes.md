# VideoFlow 3.10.0

Performance release: worker lanes, hardlinked inputs, NVENC tuning, metrics,
and Windows performance profile.

## Artifacts

- `videoflow-3.10.0-linux-x86_64`
- `VideoFlow-3.10.0-x86_64.AppImage`
- `VideoFlow-3.10.0-linux-x86_64.tar.zst`
- `sbom.json`, `SHA256SUMS`, `manifest.json`

## Performance

- One exclusive GPU lane plus a bounded CPU pool
  (`VF_GPU_CPU_WORKERS`, default 2); CPU scene analysis no longer reserves VRAM
  or blocks GPU render.
- Input artifacts are hardlinked into job directories when possible.
- `/api/overview` exposes runner queue wait, elapsed time, current and recent
  jobs.
- NVENC final encode uses HQ tune, spatial/temporal AQ, and lookahead 20;
  remote micro-clips use NVENC p4/CQ20 when available.
- Parallel worker keyframe extraction.
- faster-whisper CPU thread and worker tuning.
- Windows install sets high-performance power plan, Defender exclusions when
  admin, CPU worker default, all-profile firewall rules, and log path.
- Worker dashboard shows CPU workers and runner metrics.

## Verification

- MCP: 423 passed, 84% coverage, 35 tools, 16 resources.
- Python non-media: 2,837 passed, 1 skipped, 1 xfailed.
- Media: 29 passed, 2 skipped.
- UI: 52 Vitest, svelte-check 0, build OK.
- AppImage/onefile report `videoflow 3.10.0 (linux-x86_64)`.

## Windows worker

Use the 3.10.0 kit and run Install/repair for the performance profile and
scheduler changes. Physical RTX 3060 measurement remains required for speed
certification.
