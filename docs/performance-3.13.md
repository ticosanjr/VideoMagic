# Performance profile (3.13)

## Job progress

Every job now carries a monotonic `stage` and `progress` percentage.

Stages visible in `/jobs/{id}`, `/api/jobs`, `/api/overview` and both dashboards:

```text
preparing inputs -> reserving vram -> running -> collecting artifacts
-> writing shared outputs -> finishing
```

Handlers report finer stages through `gpu_worker.progress.report()`:

- ASR: loading model, transcribing, writing transcript;
- Short render: rendering segment N/M, concatenating and encoding;
- scene analysis: building proxy, detecting cuts, sampling scenes,
  extracting keyframes, writing manifest;
- matte: loading model, removing background, encoding matte;
- face tracking: tracking faces;
- NVENC render: encoding, finalizing.

## Queue priority and ETA

- `POST /jobs/{capability}` accepts `priority` from `-100` to `100`.
- The GPU lane and the CPU pool are priority queues; higher priority runs first,
  equal priority is FIFO.
- `/api/overview` adds `runner.queue` with position and estimated wait, plus
  per-capability average elapsed time.
- Submitting is rejected with HTTP 507 when free disk falls below
  `VF_GPU_MIN_FREE_DISK_MB` (default 2048 MB; Windows installer sets 4096).

## Model warmup

- `POST /api/warmup` preloads faster-whisper and rembg.
- The dashboard has an **Aquecer modelos** button.
- `VF_GPU_WARMUP=1` warms at startup; the Windows installer enables it.
- The rembg session is cached and registered in the model registry instead of
  being reloaded for every matte job.

## Transfers

- `VF_GPU_SHARED_LOCAL_ROOT` plus the worker `shared_root` enable automatic
  shared-mount inputs when `transport` is `auto`.
- Files under the local shared root are sent as relative shared paths and are
  not uploaded.
- Uploads are deduplicated by SHA-256 before a byte is sent.
- Multiple independent inputs upload through a bounded pool
  (`VF_GPU_UPLOAD_WORKERS`, default 3).
- Every routed result reports `transfer` with upload/download bytes, seconds,
  deduplicated uploads, and MB/s.

## Scene analysis

The proxy is decoded once at 360p/10 fps. Visual sampling now walks that proxy
sequentially instead of seeking the decoder per sample, and the number of
analysis frames per scene is bounded by `visual_max_frames` (default 10).
Keyframes remain parallel and still come from the original source.

## Retention

- `VF_GPU_JOB_RETENTION_HOURS` (default 168) controls finished job retention.
- Cleanup runs at startup and once per hour.

## Targets

- scene detection: <=45 s per source hour;
- Short 60 s on RTX 3060: <=20 s;
- queue wait: <10 s;
- unexpected local fallback: 0 when the worker is healthy.

Physical RTX numbers still require the Windows machine.
