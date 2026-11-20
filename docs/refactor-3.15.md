# Refactor and throughput (3.15)

## Worker handler package

The 1,360-line `handlers_gpu.py` was split into `gpu_worker/gpu_handlers/`:

```text
common.py    FFmpeg/NVENC helpers, command runners
asr.py       faster-whisper ASR and forced alignment
matte.py     cached rembg sessions and segment matte
render.py    NVENC master render and Short micro-clips
vision.py    face tracking and blur audit
scene.py     scene detect, visuals, keyframes, manifest
registry.py  capability registration and warmup
```

`handlers_gpu.py` remains as a compatibility facade, including private helpers
used by tests. Public imports are unchanged.

## Worker HTTP helpers

- `http_auth.py` owns client classification, allowlists, and token-file reads.
- `telemetry.py` owns disk, log rotation, log tail, LAN URLs, and current-job
  projection.
- `app.py` keeps routing and orchestration.

## Dashboard assets

The embedded dashboard is now:

```text
ui/index.html
ui/app.css
ui/app.js
```

Static files are served by the existing `/ui` mount. A local-only token
rotation button appears when the dashboard is opened on loopback.

## Parallel Short segments

Micro-clips are independent, so the local renderer and the worker handler run
them through a bounded pool:

```text
VF_SHORT_SEGMENT_WORKERS=2
```

Custom runners and tests stay sequential. Cached micro-clips are linked first,
then pending segments render in parallel, then concat/final encode runs once.

## Parallel artifact downloads

`GPUWorkerClient.download_all` downloads independent artifacts with a bounded
default of three workers while preserving the manifest order.

## Test robustness

The CPU-pool concurrency test now uses a barrier instead of a wall-clock
threshold, so it verifies real parallelism without being timing-flaky.
