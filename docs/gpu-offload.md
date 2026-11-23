# GPU offload architecture

VideoFlow keeps project state, editing, and export orchestration on the Linux
controller. A Windows worker executes only the capabilities you explicitly
allow.

```text
Linux controller                         Windows GPU worker
----------------                         ------------------
ProjectState + SQLite                    FastAPI /health /jobs /artifacts
ComputeRouter                             HandlerRegistry
  health TTL 1s / circuit 2s               faster-whisper (CUDA)
  VRAM cost per capability                 FFmpeg h264_nvenc
  remote → local fallback                  rembg CUDA
  execution_node telemetry                 OpenCV face tracking
        │                                          │
        ├── shared mount (preferred) ──────────────┤
        └── chunked HTTP upload/download ──────────┘
```

## Placement

`ComputeRouter` chooses remote only when the worker is healthy, advertises the
capability, has enough free VRAM, and is below the queue limit. Any remote
failure invalidates health and opens a short circuit; the next item runs local.
`execute_batch()` is the per-item fallback path for batches: a worker that dies
after two clips does not abort the other three.

## Transport

- **shared_mount** — the controller asks for `shared_outputs`; the worker writes
  atomically into the same folder and returns relative paths. Use it for
  longform masters and matte clips.
- **lan_stream** — chunked multipart upload and downloaded artifacts. Use it for
  short clips and one-off ASR.
- **discovery** — the worker broadcasts a UDP beacon on 8767; the controller
  keeps a 10-second peer table.

## Security

The worker requires `X-VF-Token` on every route except `/health`. Tokens live in
the controller secret store and in the personal Windows kit. The kit is never
published with a release.

## Acceptance status

The automated gates are green. A 3.4.0 release requires a real Windows NVIDIA
worker for the ASR, NVENC, and matte thresholds; see
[windows-worker.md](windows-worker.md).
