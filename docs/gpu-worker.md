# Hybrid compute and GPU worker

VideoFlow can place selected capabilities on a Windows GPU worker over the LAN.
The local pipeline remains the default and always owns project state. The
Windows bootstrap is described in [windows-worker.md](windows-worker.md).

## Placement

`ComputeRouter` reads:

| Variable | Default | Meaning |
| --- | --- | --- |
| `VF_COMPUTE_MODE` | `auto` | `auto`, `remote_preferred`, or `local_only` |
| `VF_GPU_WORKER_URL` | empty | Worker base URL, for example `http://192.168.1.45:8766` |
| `VF_GPU_WORKER_TOKEN` | empty | Shared pairing token |
| `VF_GPU_HEALTH_TTL_SEC` | `1` | Cached health lifetime |
| `VF_GPU_HEALTH_TIMEOUT_SEC` | `0.3` | Health probe timeout |
| `VF_GPU_CIRCUIT_SEC` | `2` | Cooldown after a transport failure |
| `VF_GPU_MIN_VRAM_MB` | `2048` | Minimum free VRAM for any remote job |
| `VF_GPU_MAX_QUEUE` | `2` | Queue depth above which the router stays local |

The router estimates VRAM per capability (`asr` 3277 MB, `render_nvenc`
820 MB, `segment_matte` 1536 MB, `face_track` 1024 MB, and so on). A worker must
advertise the capability, have enough free VRAM, and remain below the queue
limit.

`local_only` never performs network I/O. `auto` and `remote_preferred` fall back
to local execution with a reason. A remote failure invalidates the health cache
and opens the circuit for `VF_GPU_CIRCUIT_SEC`.

## VRAM, transport, and discovery

### VRAM budget and model eviction

The worker enforces `VF_GPU_MAX_VRAM_MB` (default 10240) with a
`VF_GPU_VRAM_RESERVE_MB` reservation (default 512). Before each job it estimates
the capability cost and asks `ModelRegistry` to unload least-recently-used
models until the job fits. If it still does not fit, the job fails with an
actionable VRAM error. `VF_GPU_MODEL_TTL_SEC` defaults to 300 seconds.

`POST /models/unload` frees one named model or every loaded model. Health
reports `vram_used_mb`, `vram_budget_mb`, and per-model `vram_mb`.

### Shared outputs and streaming

`JobSubmission.shared_outputs` asks the worker to write results directly into
the mounted workspace. Paths must be relative, cannot contain `..`, and their
parent directory must already exist. The worker copies each produced artifact
atomically and reports the relative paths in `shared_artifacts`.

When the mount is unavailable, `GPUWorkerClient` streams uploads in chunks
instead of reading a file into memory. Prefer the shared mount for longform
masters and HTTP streaming for short clips.

`POST /shared/validate` checks a write path by creating and removing a probe
file.

### Discovery

With `VF_GPU_DISCOVERY=1` the worker broadcasts a UDP beacon every two seconds
on `VF_GPU_ADVERTISE_PORT` (default 8767). The beacon includes `worker_id`,
hostname, LAN address, port, GPU, VRAM, queue, capabilities, and version.
`vf_compute.discovery.GpuDiscovery` keeps a 10-second TTL peer table, and
`ComputeRouter.discover()` listens briefly and returns peers.

## Setup → GPU acceleration

The Setup tab pairs a worker, downloads the Windows kit, and configures
placement. It has four cards:

1. **Pairing** — LAN scan, manual URL/token, connect/disconnect, and the
   personal Windows kit download.
2. **What runs on the GPU** — per-capability toggles, including ASR, NVENC,
   matte, face tracking, stems, upscale, TTS, and ComfyUI.
3. **Shared folder** — enable the mount, set the Windows path, and validate
   read/write.
4. **Resources** — VRAM cap, local fallback, discovery, loaded models, queue,
   and “Free GPU memory”.

The header pill has three live states: ready, busy, and local/offline. Its
popover switches between automatic placement and forced local mode and links to
the Setup tab.

## Worker capabilities

With `VF_GPU_BUILTIN_HANDLERS=1` the worker registers Python handlers for:

| Capability | Backend | Output |
| --- | --- | --- |
| `asr` | faster-whisper float16 CUDA | `transcript.json` with word timings |
| `forced_align` | faster-whisper word timestamps | `alignment.json` |
| `render_nvenc` | FFmpeg `h264_nvenc` | MP4 with optional burned ASS |
| `segment_matte` | rembg | PNG or WebM with alpha |
| `face_track` | OpenCV Haar | normalized `tracking.json` keyframes |
| `vision_blur` | OpenCV Laplacian | `blur.json` frame scores |
| `scene_analyze` | PySceneDetect/FFmpeg + OpenCV | `scenes_manifest.json` + `scene_keyframes.zip` |
| `short_render` | FFmpeg NVENC | final 1080x1920 MP4 |

`tts`, `music`, `sfx`, `stems`, `upscale`, `diarize`, and `comfyui` remain
available through their configured command/HTTP handlers. Missing dependencies
are reported in `/health` under `unavailable_capabilities` with a reason.

Worker variables:

```text
VF_GPU_TOKEN=...
VF_GPU_PORT=8766
VF_GPU_WORKER_ID=BERNA-WIN-SERVE
VF_GPU_BUILTIN_HANDLERS=1
VF_GPU_FFMPEG=C:\videoflow\ffmpeg.exe
VF_GPU_ASR_MODEL=large-v3-turbo
VF_GPU_ASR_DEVICE=cuda
VF_GPU_ASR_COMPUTE_TYPE=float16
VF_GPU_MODEL_TTL_SEC=300
VF_GPU_MAX_VRAM_MB=10240
VF_GPU_VRAM_RESERVE_MB=512
VF_GPU_DISCOVERY=1
VF_GPU_ADVERTISE_PORT=8767
VF_GPU_SHARED_ROOT=\\server\videoflow
```

## Status and telemetry

`vf_capabilities` returns a `compute` object and a `compute_router` manifest
entry with:

- `mode`, `worker_url`, `execution_node`;
- `available`, `worker_id`, `hostname`, `ip_local`, `port`;
- `gpu_name`, VRAM free/used/total, utilization, temperature;
- remote capabilities, loaded models, and queue depth.

`ComputeRouter.execute(capability, remote_fn, local_fn)` returns the caller
value plus `execution_node`, `fallback_reason`, `remote`, and `elapsed_sec`.
Job results may persist that block under `execution`.

## Security

- The worker requires `X-VF-Token` on every route except `/health`.
- Tokens are compared with `secrets.compare_digest` and are never returned.
- The worker binds to `0.0.0.0`; use the private LAN and a host firewall rule.
- Artifact ids and shared paths are validated before use.
