# VideoFlow 3.15.0

Refactor and throughput release: split worker handlers, separated dashboard
assets, extracted HTTP helpers, parallel Short segments, and parallel artifact
downloads.

## Artifacts

- `videoflow-3.15.0-linux-x86_64`
- `VideoFlow-3.15.0-x86_64.AppImage`
- `VideoFlow-3.15.0-linux-x86_64.tar.zst`
- `VideoFlow-Windows-GPU-Worker-3.15.0.zip`
- `sbom.json`, `SHA256SUMS`, `manifest.json`

## Worker refactor

- `handlers_gpu.py` split into `gpu_worker/gpu_handlers/`:
  common, ASR, matte, render, vision, scene, registry.
- `handlers_gpu.py` remains an import-compatible facade, including private
  helpers used by tests.
- HTTP auth/allowlist/token helpers moved to `http_auth.py`.
- Disk/log/LAN/job telemetry moved to `telemetry.py`.
- Worker dashboard split into `index.html`, `app.css`, and `app.js`.
- Local dashboard exposes token rotation when opened on loopback.

## Performance

- Short micro-clips render in a bounded parallel pool locally and on the
  worker. Default: 2 workers (`VF_SHORT_SEGMENT_WORKERS`).
- Cached segments are linked before rendering; concat/final encode runs once.
- `download_all` downloads independent artifacts with a bounded pool of three
  while preserving manifest order.

## Test reliability

- CPU-pool concurrency is verified with a barrier instead of a wall-clock
  threshold.
- Dashboard static asset test covers `/ui/app.js` and `/ui/app.css`.

## Verification

- Python non-media: 2,865 passed, 1 skipped, 1 xfailed.
- MCP: 424 passed, 84% coverage, 35 tools, 16 resources.
- Media: 29 passed, 2 skipped.
- UI: 56 Vitest, svelte-check 0, build OK.
- Public Windows kit contains the worker, scene-rules, and split UI assets.

## Pending

Physical RTX 3060 NVENC certification still requires the Windows machine.
