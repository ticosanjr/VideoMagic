# VideoFlow 3.13.0

Live job progress, priority queues, model warmup, adaptive transfers, and a
faster scene pipeline.

## Artifacts

- `videoflow-3.13.0-linux-x86_64`
- `VideoFlow-3.13.0-x86_64.AppImage`
- `VideoFlow-3.13.0-linux-x86_64.tar.zst`
- `VideoFlow-Windows-GPU-Worker-3.13.0.zip`
- `sbom.json`, `SHA256SUMS`, `manifest.json`

## Progress and queue

- Jobs expose monotonic `stage` and `progress`.
- Handler-level stages: ASR model/transcribe/write, matte, scene proxy/cuts/
  sampling/keyframes, Short segment N/M and final encode, face tracking, NVENC.
- `POST /jobs/{capability}` accepts `priority` (`-100..100`).
- GPU and CPU lanes are priority queues; `/api/overview` reports queue position,
  ETA, and per-capability average elapsed time.
- HTTP 507 backpressure when worker disk is below
  `VF_GPU_MIN_FREE_DISK_MB`.

## Warmup

- `POST /api/warmup` preloads faster-whisper and rembg.
- Dashboard button **Aquecer modelos**.
- `VF_GPU_WARMUP=1` warms on startup; the Windows installer enables it.
- rembg sessions are cached and registered in the model registry.

## Transfers

- Automatic shared-mount inputs when `VF_GPU_SHARED_LOCAL_ROOT` and the worker
  shared root are present.
- Files already on the mount are not uploaded.
- SHA-256 deduplication before transfer.
- Bounded parallel uploads (`VF_GPU_UPLOAD_WORKERS`, default 3).
- Per-result `transfer` metrics: upload/download bytes, seconds, dedup count,
  MB/s.

## Scene pipeline

- 360p/10 fps proxy.
- One sequential decode pass for visual sampling instead of per-sample seeks.
- `visual_max_frames` bounds analysis frames (default 10).
- Parallel keyframe extraction from the original source.

## Retention

- Finished jobs cleaned hourly and at startup.
- `VF_GPU_JOB_RETENTION_HOURS` default 168.

## Verification

- MCP: 424 passed, 84% coverage, 35 tools, 16 resources.
- Python non-media: 2,844 passed, 1 skipped, 1 xfailed.
- Media: 29 passed, 2 skipped.
- UI: 52 Vitest, svelte-check 0, build OK.
- AppImage/onefile report `videoflow 3.13.0 (linux-x86_64)`.
- Public Windows kit is tokenless and includes the 3.13.0 worker wheel.

## Windows

Download the 3.13.0 kit, extract to a short path, run `VideoFlowGPU.bat`, then
Install/repair and Start. The dashboard shows stage/progress, queue ETA, disk,
warmup, and runner metrics.

Physical RTX 3060 NVENC certification still requires the Windows machine.
