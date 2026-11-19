# Network offload

Heavy work is routed through the compute router, never hardcoded to the local
machine.

## Placement

- `auto`: remote Windows worker when healthy and capable; local fallback is
  marked `degraded`.
- `remote`: prefer the worker but allow a local fallback.
- `remote_only`: fail if the worker or capability is unavailable.
- `local` / `local_only`: no network I/O.

## Heavy capabilities

```text
asr
forced_align
short_render
render_nvenc
segment_matte
face_track
scene_analyze
```

`scene_analyze` runs the CPU-heavy detection and layout pass on the worker and
returns the manifest plus a keyframe archive. `short_render` receives the
tokenised micro-clip/concat/final commands, executes them on the worker FFmpeg
with NVENC, and returns the finished MP4. Local `libx264` is the automatic
fallback and records `degraded=true` with the reason.

## Contract

Every routed job reports:

```json
{
  "execution_node": "remote_gpu",
  "device": "remote_gpu",
  "degraded": false,
  "degraded_reason": "",
  "elapsed_sec": 12.3
}
```

The worker URL/token come from `gpu.json` or environment, never from a frozen
`opencode.json` placeholder. Shared mount is an accelerator; a failed shared
write falls back to HTTP automatically.
