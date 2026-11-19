# Hybrid compute and GPU worker

VideoFlow can place selected capabilities on a Windows GPU worker over the LAN.
The local pipeline remains the default and always owns project state.

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

## Worker capabilities

With `VF_GPU_BUILTIN_HANDLERS=1` the worker registers Python handlers for:

| Capability | Backend | Output |
| --- | --- | --- |
| `asr` | faster-whisper float16 CUDA | `transcript.json` with word timings |
| `render_nvenc` | FFmpeg `h264_nvenc` | MP4 with optional burned ASS |
| `segment_matte` | rembg | PNG or WebM with alpha |
| `face_track` | OpenCV Haar | normalized `tracking.json` keyframes |

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
