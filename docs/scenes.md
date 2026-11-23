# Scene intelligence

Module A turns one recording into a cached, render-ready scene map. It is
deterministic and CPU-first; the expensive visual pass is exposed to the
network worker only when its `scene_analyze` capability is available.

## Flow

```text
source
  -> 360p proxy
  -> PySceneDetect AdaptiveDetector (min_scene_len = 1.5 s)
  -> fuse with decupage jumps (>= 2 s)
  -> sample 3-20 frames per scene
  -> MediaPipe Face (Haar fallback) + Canny + Laplacian
  -> layout classification
  -> one 544 px JPEG per scene
  -> scenes_manifest.json
  -> timeline_supercontext.json
```

Run it after `ingest` and, when available, after `decupage.snap`:

```text
vf_run(project_id="...", steps=["scene.analyze"],
        params={"source_topology": "auto", "force": False})
```

`decupage_plan_path` or `context.metadata["decupage_plan"]` is optional. When
present, its cuts become `DECUPAGEM_JUMP` boundaries and its ASUs populate
`timeline_supercontext.json`.

## Compute placement

`scene.analyze` accepts `compute_policy`:

| Policy | Behavior |
| --- | --- |
| `auto` (default) | Use the worker when `scene_analyze` is healthy; otherwise run locally and mark `degraded=true`. |
| `local` | Never touch the network. |
| `remote` | Prefer the worker; local fallback is recorded. |
| `remote_only` | Fail when the worker or capability is unavailable. |

The worker builds its own 360p proxy, detects cuts, classifies layouts, and
returns `scenes_manifest.json` plus `scene_keyframes.zip`. The local client
validates the manifest, extracts keyframes safely, rewrites their paths, and
writes the same cache as a local run (`engine=remote_scene_analyze`). The
placement is recorded in `context.metadata["scenes_compute"]`.

## Layouts

| Layout | Rule |
| --- | --- |
| `DUAL_CANVAS_OBS` | 3840x1080 or aspect near 3.55 |
| `TALKING_HEAD` | face area >= 0.055 |
| `SCREEN_SHARE_PIP` | face present but smaller |
| `SCREEN_SHARE_FULL` | no face and edge density >= 0.08 |
| `BROLL_OR_FOOTAGE` | no face and low activity |

Hints: `LONG_STATIC_SHOT` (talking head >= 12 s), `SCENE_TYPE_SWITCH`,
`PROTECT_FROM_BROLL`, `LOW_SHARPNESS_WARNING`, `SAFE_FOR_BROLL`, and
`DUAL_CANVAS_READY`.

## Cache

```text
<project output>/scenes/<video_sha256>/
  proxy_360.mp4
  keyframes/SC_0001.jpg
  scenes_manifest.json
  scenes_cache.json
  timeline_supercontext.json
```

`scenes_cache.json` stores the cache key (detector version, SHA-256, threshold,
minimum scene length, topology, keyframe size). Changing any of those
invalidates both the manifest and the JPEGs. Re-rendering a Short with different
layouts reuses the same scene map.

## MCP surface

One consolidated tool keeps the profile small:

```text
vf_scenes(
  action="analyze" | "manifest" | "keyframe" | "supercontext" | "cache",
  project_id,
  video_id="",
  video_path="",
  scene_id="",
  decupage_plan_path="",
  source_topology="auto",
  threshold=3.0,
  min_scene_len_sec=1.5,
  keyframe_size=544,
  compute_policy="auto",
  force=False,
  wait=True,
  timeout_sec=1800
)
```

- `analyze` queues `scene.analyze` and, when `wait=true`, returns the summary.
- `manifest` returns the summary, a page of scenes (`offset`/`limit`), and paths.
- `keyframe` returns metadata and the file path only, never base64.
- `supercontext` returns the fused scene/ASU JSON.
- `cache` reports the cache key, engine, keyframe count, and missing files.

Resources:

```text
vf://projects/{project_id}/scenes
vf://projects/{project_id}/scenes/{scene_id}/keyframe
```

Both are read-only JSON views. The MCP never forces an output folder or a
particular render path; custom project outputs remain valid.

## Dependencies

```bash
uv sync --extra scene
```

- `scenedetect` drives cut detection. Without it the engine falls back to the
  FFmpeg scene score and records `engine=ffmpeg_fallback` plus a warning.
- `mediapipe` improves face boxes. Without it the OpenCV Haar cascade is used.
- `opencv-python-headless` is required for both keyframes and metrics.

The step never emits base64 images. `scenes_manifest.json` and
`timeline_supercontext.json` carry paths only; an agent opens a keyframe on
demand.
