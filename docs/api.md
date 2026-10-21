# HTTP API

Base URL: `http://127.0.0.1:8765`. No authentication in v1. Bind only to
loopback.

Implemented today:

- `GET /health`
- `GET /api/v1/system`
- `GET /api/v1/capabilities`
- `GET /api/v1/fs/roots`, `GET /api/v1/fs/list`, `POST /api/v1/fs/mkdir`
- `GET /api/v1/media/probe`
- `GET /api/v1/assets/fonts`, `POST /api/v1/assets/fonts`
- `GET /api/v1/assets/images`, `POST /api/v1/assets/images`
- `GET /api/v1/assets/music`, `POST /api/v1/assets/music`
- `GET/PUT/DELETE /api/v1/brand-templates`, `POST /api/v1/brand-templates/{name}/apply`
- Short thumbnail generation and download
- `POST /api/v1/jobs`, `GET /api/v1/jobs`, `GET /api/v1/jobs/{id}`,
  `POST /api/v1/jobs/{id}/cancel`, `GET /api/v1/jobs/{id}/events`
- `POST /api/v1/projects`, `GET /api/v1/projects`,
  `GET /api/v1/projects/{id}/state`
- Project media, module config/enabled, run, cancel, events, transcript,
  overrides, exports, and preset application
- `GET /api/v1/presets`, `GET /api/v1/presets/{name}`,
  `PUT /api/v1/presets/{name}`
- `GET /mcp/` (MCP Streamable HTTP) and `GET /` (rack UI when built)

Per-module reruns are the one project route reserved for the next engine pass.
They return `501 not_implemented`; the full project run is implemented.

## 1. Conventions

- JSON in, JSON out. UTF-8.
- Job times are integers in state: frames for video, samples for audio.
- Success: `200` or `202`. Validation: `422`.
- Expected failures:

```json
{
  "detail": {
    "ok": false,
    "code": "path_not_allowed",
    "message": "Path is outside the allowlist: /etc/passwd"
  }
}
```

| Status | Codes |
| --- | --- |
| 403 | `path_not_allowed`, `permission_denied` |
| 404 | `job_not_found`, `project_not_found`, `preset_not_found`, `unknown_module`, `transcript_not_found`, `path_not_found` |
| 409 | `job_already_running`, `module_bypassed`, `media_not_registered`, `state_not_ready`, `directory_exists` |
| 422 | validation, `invalid_time`, `media_not_found`, `transcript_required`, `invalid_override`, `word_overrides_not_supported`, `invalid_config`, `invalid_preset_name`, `preset_invalid`, `export_failed`, `short_edit_failed`, `not_a_directory`, `invalid_directory_name` |
| 429 | `job_queue_full` |
| 500 | `project_state_invalid`, `filesystem_error` |
| 501 | `not_implemented` (per-module reruns) |

## 2. Health and system

```http
GET /health
```

```json
{ "status": "ok", "service": "videoflow", "version": "0.21.2" }
```

```http
GET /api/v1/system
```

```json
{
  "ok": true,
  "version": "0.21.2",
  "home": "/home/editor/.videoflow",
  "allowed_roots": ["/home/editor", "/home/editor/projects", "/home/editor/.videoflow"],
  "ffmpeg": "/usr/bin/ffmpeg",
  "ffprobe": "/usr/bin/ffprobe"
}
```

`allowed_roots` comes from `VIDEOWFLOW_ALLOWED_ROOTS` (path-separator list) or
defaults to home, cwd, and the portable data directory.

### Capabilities and provider policy

```http
GET /api/v1/capabilities?allow_external=true
```

Returns feature availability plus the effective external-service policy. A
blocked provider includes a reason string. `VIDEOWFLOW_ALLOW_EXTERNAL=0` is a
global kill switch; localhost providers remain available.

### Filesystem browser

The rack uses these routes instead of uploading media. Every path passes the
same allowlist as a job; an entry with a symlink outside the allowlist is not
returned. The browser is a convenience, not a new trust boundary.

```http
GET /api/v1/fs/roots
```

```json
{
  "ok": true,
  "roots": [
    {
      "name": "Home",
      "path": "/home/editor",
      "exists": true,
      "writable": true
    }
  ]
}
```

```http
GET /api/v1/fs/list?path=/home/editor/video&mode=file&extensions=mp4,mov&q=interview
```

`mode` is `file` or `directory`. File mode returns subdirectories plus matching
files; directory mode returns only directories. `extensions` is a
comma-separated list, `q` is a case-insensitive name filter, `show_hidden=true`
includes dot entries, and `limit` caps the result (default 500, maximum 2,000).

```json
{
  "ok": true,
  "path": "/home/editor/video",
  "name": "video",
  "parent": { "name": "editor", "path": "/home/editor" },
  "breadcrumbs": [
    { "name": "Home", "path": "/home/editor" },
    { "name": "video", "path": "/home/editor/video" }
  ],
  "roots": [],
  "entries": [
    {
      "name": "interview.mp4",
      "path": "/home/editor/video/interview.mp4",
      "kind": "file",
      "size_bytes": 124000000,
      "modified_at": "2026-10-20T18:00:00+00:00",
      "extension": ".mp4",
      "selectable": true,
      "is_symlink": false
    }
  ],
  "truncated": false,
  "can_write": true,
  "mode": "file"
}
```

```http
POST /api/v1/fs/mkdir
Content-Type: application/json
```

```json
{ "parent": "/home/editor/video", "name": "interview-videoflow" }
```

Returns `201` with `{ "ok": true, "entry": {...} }`. Names are one portable path
segment: no separators, `..`, dot-only names, control characters, Windows
reserved names, or trailing spaces/dots. Existing entries return
`directory_exists`.

```http
GET /api/v1/media/probe?path=/home/editor/video/interview.mp4
```

Returns the path, name, size, and the same `MediaInfo` shape used by jobs. It is
used by the picker to show duration, resolution, frame rate, and audio rate.

## 3. Jobs (implemented)

### Start

```http
POST /api/v1/jobs
Content-Type: application/json
```

```json
{
  "source": "/media/interview.mp4",
  "output": "/projects/interview-edit",
  "noise_db": -30,
  "min_silence_ms": 400,
  "min_speech_ms": 100,
  "vad_engine": "auto",
  "speech_threshold": 0.5,
  "speech_pad_before_ms": 120,
  "speech_pad_after_ms": 150,
  "jcut": true,
  "lcut": false,
  "offset_ms": 200,
  "crossfade_ms": 20,
  "fade_in_ms": 20,
  "fade_out_ms": 20,
  "fade_curve": "logarithmic",
  "handle_check": true,
  "zooms": true,
  "zoom_mode": "alternate_cuts",
  "zoom_min_scale": 1.0,
  "zoom_max_scale": 1.5,
  "punch_in_scale": 1.15,
  "anchor_point": "upper_third",
  "progressive_zoom": false,
  "pan_direction": "none",
  "dialect": "1.9",
  "export_targets": ["resolve", "premiere", "kdenlive"],
  "transcript": "/media/interview.srt",
  "cull_retakes": true,
  "strictness": "balanced",
  "retake_strategy": "keep_last",
  "context_window": 15,
  "llm_base_url": "http://localhost:11434/v1",
  "llm_model": "qwen2.5:7b-instruct",
  "shorts": true,
  "shorts_count": 3,
  "shorts_min_count": 3,
  "shorts_min_sec": 30,
  "shorts_max_sec": 60,
  "shorts_subtitles": true,
  "shorts_selection_mode": "auto",
  "shorts_prompt": "pricing and margins",
  "shorts_reprompt": "more energy",
  "shorts_prompt_mode": "replace",
  "shorts_hook_mode": "off",
  "shorts_reframe_mode": "center_crop_9_16",
  "shorts_remove_fillers": false,
  "shorts_filler_words": ["hum", "hmm", "uh", "um"],
  "shorts_aspect": "9:16",
  "shorts_source_start_sec": 0,
  "shorts_source_end_sec": null,
  "allow_external_services": false,
  "allowed_external_hosts": [],
  "audio_enhance": false,
  "audio_highpass_hz": 80,
  "audio_denoise": true,
  "audio_denoise_db": 12,
  "audio_noise_floor_db": -30,
  "audio_loudnorm": true,
  "audio_target_lufs": -16.0,
  "audio_true_peak_db": -1.5,
  "overlay_enabled": false,
  "overlay_asset": "",
  "overlay_position": "bottom_right",
  "overlay_margin_px": 32,
  "overlay_width_ratio": 0.18,
  "overlay_opacity": 0.9,
  "music_enabled": false,
  "music_asset": "",
  "music_volume": 0.18,
  "music_ducking": true,
  "music_fade_in_ms": 250,
  "music_fade_out_ms": 500,
  "intro_enabled": false,
  "intro_asset": "",
  "intro_duration_sec": 2.0,
  "outro_enabled": false,
  "outro_asset": "",
  "outro_duration_sec": 2.0,
  "caption_font_family": "Arial",
  "caption_font_size": 72,
  "caption_font_weight": "bold",
  "caption_italic": false,
  "caption_uppercase": false,
  "caption_primary_color": "#FFFFFF",
  "caption_highlight_color": "#FFD400",
  "caption_outline_color": "#000000",
  "caption_outline_width": 4,
  "caption_shadow_color": "#000000",
  "caption_shadow_offset": 2,
  "caption_shadow_opacity": 0.6,
  "caption_background_color": "#000000",
  "caption_background_opacity": 0.0,
  "caption_background_padding": 0,
  "caption_alignment": 2,
  "caption_position_x": 0.5,
  "caption_position_y": 0.78,
  "caption_max_width": 0.9,
  "caption_animation": "none",
  "caption_word_timing": "engine",
  "caption_censor_enabled": false,
  "caption_censor_words": ["porra", "merda"],
  "caption_censor_replacement": "***",
  "caption_keyword_highlight_enabled": false,
  "caption_keyword_color": "#00E5FF",
  "caption_keyword_words": [],
  "caption_emoji_enabled": false,
  "caption_emoji_map": { "money": "💰" },
  "caption_brand_vocabulary": { "video flow": "VideoFlow" },
  "overrides": [
    { "sentence_id": 4, "action": "keep" },
    { "sentence_id": 7, "action": "discard" }
  ],
  "transcribe": true,
  "asr_base_url": "http://localhost:8000/v1",
  "asr_model": "whisper-1",
  "asr_language": "pt",
  "whisper_engine": "auto",
  "whisper_model_size": "small",
  "whisper_device": "cpu",
  "whisper_compute_type": "int8",
  "whisper_vad_filter": false,
  "whisper_model": null,
  "faster_whisper_model": null
}
```

`vad_engine` selects `auto`, `silero`, or `ffmpeg`. `auto` uses the bundled
Silero model when ONNX Runtime and the model are available, otherwise FFmpeg.
`speech_threshold` applies to Silero; `speech_pad_before_ms` and
`speech_pad_after_ms` apply to both engines. Explicit `silero` fails when the
model or runtime is missing instead of silently downgrading.

`zoom_min_scale` and `zoom_max_scale` bound the punch-in; `punch_in_scale`
must stay inside that window. Fade fields configure the first/last audio ramps
and the join crossfade curve.

`shorts_min_count` is a minimum, not a cap; `shorts_count` is the target and
maximum. If the material cannot produce the minimum, the result includes a
warning. `shorts_selection_mode` is `auto`, `llm`, or `heuristic`.
`caption_*` fields configure the burned Shorts captions/karaoke. Word timings
come from the transcript engine; `caption_word_timing=proportional` distributes
a sentence's duration across its words, and `sentence` disables karaoke.

`transcript` is optional and is resolved through the same allowlist as media.
When `cull_retakes` is true and `VIDEOWFLOW_LLM_BASE_URL` is set, the worker
uses the OpenAI-compatible endpoint; otherwise only exact repeated text is
culled.

`overrides` is applied after the retake guard: `keep` removes a sentence from
the cull set, `discard` adds it. Manual decisions win over the model and guard.
Overrides require a transcript.

When `transcribe` is true and no SRT is supplied, an `asr_base_url` selects the
remote path: the worker posts the analysis WAV to
`<asr_base_url>/audio/transcriptions` with `response_format=verbose_json`. The
API key is read from `VIDEOWFLOW_ASR_API_KEY`; the base URL falls back to
`VIDEOWFLOW_ASR_BASE_URL`.

With no URL, `whisper_engine` selects the local path:

- `auto` uses Faster-Whisper when the optional package and selected model
  directory are present, then falls back to whisper.cpp.
- `faster-whisper` requires Faster-Whisper and the model; it never silently
  downgrades.
- `whisper.cpp` forces the bundled CLI and GGML model.

`whisper_model_size` selects `tiny`, `base`, `small`, `medium`, or `large-v3`.
`whisper_device` is `cpu` or `cuda`; `whisper_compute_type` is `int8`,
`float16`, or `float32`. `whisper_vad_filter` enables Faster-Whisper's internal
VAD and should stay false when module 02 is enabled. An empty
`faster_whisper_model` uses the bundled model for the chosen size; a directory
selects a local CTranslate2 model. An empty `whisper_model` uses the bundled
GGML tiny model; a path selects another GGML file. SRT wins if present.

The job result and `run.json` report `transcript_source` as `faster-whisper`,
`whisper`, `asr`, `srt`, or `project`.

`source` and `output` are resolved through the path allowlist. Both are required.
The output directory is created by the worker.

Response `202`:

```json
{
  "ok": true,
  "job": {
    "job_id": "4cd1312c-...",
    "status": "running",
    "progress": 0,
    "stage": "queued",
    "message": "Waiting for a worker",
    "source": "/media/interview.mp4",
    "output": "/projects/interview-edit",
    "options": { "noise_db": -30.0, "min_silence_ms": 400, "jcut": true },
    "result": null,
    "error": null,
    "created_at": "2026-10-19T21:09:48.120+00:00",
    "started_at": "2026-10-19T21:09:48.130+00:00",
    "finished_at": null,
    "duration_ms": 410,
    "log_count": 12,
    "stages": [
      {
        "id": "ingest",
        "module": "ingest",
        "label": "Ingest",
        "status": "succeeded",
        "progress": 100,
        "started_at": "2026-10-19T21:09:48.131+00:00",
        "finished_at": "2026-10-19T21:09:48.310+00:00",
        "duration_ms": 179,
        "message": "PCM ready",
        "error": null
      }
    ]
  }
}
```

The default concurrency is two active jobs per process. A third start returns
`429 job_queue_full`.

### List and read

```http
GET /api/v1/jobs
GET /api/v1/jobs/{job_id}
```

`GET` returns `{"ok": true, "job": {...}}`. The list is newest first.

### Cancel

```http
POST /api/v1/jobs/{job_id}/cancel
```

Cancellation is cooperative. The worker stops between probe, extraction, VAD,
timeline, export, and state stages. A running FFmpeg process is not killed
mid-stage.

### Logs

```http
GET /api/v1/jobs/{job_id}/logs
GET /api/v1/jobs/{job_id}/logs?module=vad&level=error&limit=200
GET /api/v1/jobs/{job_id}/logs?download=1
```

The JSON response carries `logs`, `count`, and `total`. Each line has
`timestamp`, `level`, `module`, and `message`. The download form returns plain
text with `Content-Disposition: attachment`.

Logs are bounded at 1,000 lines per job. The FFmpeg command and the last 50
stderr lines are captured; secrets are redacted. `job.log` is also written to the
job output directory.

### State

```http
GET /api/v1/jobs/{job_id}/state
```

Returns the `project_state.json` written by the job. The UI uses it for the
inspector (transcript sentences, culls, guard restorations). If the job has not
written state yet, the route returns `404 state_not_found`.

### Edit a short

```http
POST /api/v1/jobs/{job_id}/shorts/{index}/edit
Content-Type: application/json
```

```json
{
  "title": "Edited hook",
  "start_sec": 1.0,
  "end_sec": 5.0,
  "aspect_ratio": "1:1",
  "burn_subtitles": true,
  "caption_style": { "font_size": 80, "primary_color": "#FF0000" }
}
```

The source must come from a succeeded job. The endpoint writes a new MP4 and
ASS under `shorts/edited/`, updates `shorts.json` and the job result, and leaves
the original render available. `caption_style` is merged into the project style.

### Brand templates

```http
GET /api/v1/brand-templates
PUT /api/v1/brand-templates/studio
POST /api/v1/brand-templates/studio/apply
DELETE /api/v1/brand-templates/studio
```

A template bundles caption style, overlay, music, and intro/outro settings. A
job may pass `brand_template` to apply one server-side.

### Music

```http
GET /api/v1/assets/music
POST /api/v1/assets/music?name=track.mp3
Content-Type: application/octet-stream
<audio bytes>
```

MP3, WAV, M4A, AAC, or OGG up to 100 MB. Use the returned `name` as
`music_asset`.

### Images

```http
GET /api/v1/assets/images
POST /api/v1/assets/images?name=logo.png
Content-Type: application/octet-stream
<image bytes>
```

PNG/JPEG only, up to 15 MB. Use the returned `name` as `overlay_asset`.

### Fonts

```http
GET /api/v1/assets/fonts
POST /api/v1/assets/fonts?name=Inter.ttf
Content-Type: application/octet-stream
<font bytes>
```

Only TTF/OTF files up to 20 MB are accepted. The response includes the internal
family name used by libass; the renderer passes the asset directory as
`fontsdir`.

### Generate Short thumbnail

```http
POST /api/v1/jobs/{job_id}/shorts/{index}/thumbnail
Content-Type: application/json
```

```json
{ "time_sec": 0.5, "title": "Hook title" }
```

Extracts a frame and burns the title with the caption style. Returns the PNG
path and stores it under `short.thumbnails`.

```http
GET /api/v1/jobs/{job_id}/shorts/{index}/thumbnail
```

### Generate Short dubbing

```http
POST /api/v1/jobs/{job_id}/shorts/{index}/dub
Content-Type: application/json
```

```json
{
  "target_language": "en",
  "base_url": "http://localhost:8880/v1",
  "model": "tts-1",
  "voice": "alloy",
  "llm_base_url": "http://localhost:11434/v1",
  "llm_model": "qwen2.5:7b-instruct",
  "allow_external_services": true
}
```

Translates the Short transcript, synthesizes the translation, and mixes it over
the Short. `original_volume` defaults to `0` for dub-only.

### Generate Short voice-over

```http
POST /api/v1/jobs/{job_id}/shorts/{index}/voiceover
Content-Type: application/json
```

```json
{
  "text": "Narration text",
  "base_url": "http://localhost:8880/v1",
  "model": "tts-1",
  "voice": "alloy",
  "allow_external_services": true
}
```

Calls `/audio/speech`, lowers the original track, mixes the narration, and
updates the Short path. The API key comes from `VIDEOWFLOW_TTS_API_KEY` (or the
configured secret name).

### Generate Short metadata

```http
POST /api/v1/jobs/{job_id}/shorts/{index}/metadata
Content-Type: application/json
```

```json
{ "platform": "youtube", "tone": "engaging", "extra_hashtags": ["#pricing"] }
```

Returns a deterministic title, description, hashtags, and platform character
limits, and stores the result under `short.metadata.<platform>`.

### Download a short

```http
GET /api/v1/jobs/{job_id}/shorts/{index}
```

Returns the rendered MP4 for a shorts entry in `job.result.shorts`. The file must
live under the job output; otherwise `403 shorts_not_allowed` is returned.

### Download an artifact

```http
GET /api/v1/jobs/{job_id}/artifacts/{target}
```

`target` is `resolve`, `premiere`, or `kdenlive`. The file must live under the
job's output directory. Unknown targets return `404 artifact_not_found`; a path
outside the output returns `403 artifact_not_allowed`.

### Events

```http
GET /api/v1/jobs/{job_id}/events
Accept: text/event-stream
```

```
data: {"job_id":"...","status":"running","progress":35,"stage":"vad", ...}

data: {"job_id":"...","status":"succeeded","progress":100,"stage":"done", ...}
```

The stream emits on status, progress, or stage change and closes when the job
reaches `succeeded`, `failed`, or `cancelled`. It is polled from job state; there
is no separate event bus.

### Result

On success, `job.result` is the `run_portable` report:

```json
{
  "ok": true,
  "version": "0.21.2",
  "vad_engine": "silero",
  "speech_interval_count": 3,
  "video_segment_count": 3,
  "audio_segment_count": 3,
  "warnings": [],
  "artifacts": {
    "resolve": "/projects/interview-edit/exports/timeline.fcpxml",
    "premiere": "/projects/interview-edit/exports/timeline.xml",
    "kdenlive": "/projects/interview-edit/exports/timeline.kdenlive"
  },
  "state_path": "/projects/interview-edit/project_state.json",
  "report_path": "/projects/interview-edit/run.json"
}
```

On failure, `job.error` is the typed error payload and `status` is `failed`.

## 4. Project routes

A project is a directory. VideoFlow owns only its hidden `.videoflow/`
subdirectory and never modifies source media.

```text
/home/editor/projects/interview/
  .videoflow/
    project_state.json
    revisions/000001.json
    revisions/000002.json
    work/
    exports/
    job.log
```

The project id index is stored at
`$VIDEOWFLOW_HOME/projects.json`. Operator presets live under
`$VIDEOWFLOW_HOME/presets/`. In a frozen portable build,
`$VIDEOWFLOW_HOME` is next to the executable.

Every accepted state write increments `revision` and writes a snapshot under
`revisions/`. The snapshot is written before the canonical
`project_state.json` with a sibling temp file and atomic replace. A pipeline
job writes its final state with the expected next revision; the API snapshots
that file when the job succeeds.

### Create

```http
POST /api/v1/projects
```

```json
{
  "root": "/home/editor/projects/interview",
  "preset": "youtube-talking-head"
}
```

`preset` is optional. The response is `201`:

```json
{
  "ok": true,
  "project": {
    "project_id": "8d1d4f0e-...",
    "root": "/home/editor/projects/interview",
    "revision": 1,
    "created_at": "2026-10-20T14:00:00.000+00:00",
    "updated_at": "2026-10-20T14:00:00.000+00:00"
  },
  "state": { "schema_version": 1, "revision": 1, "...": "..." }
}
```

Creating the same root again is idempotent and returns the existing project.
Root and media paths are resolved through the allowlist.

### List and read

```http
GET /api/v1/projects
GET /api/v1/projects/{project_id}/state
```

The list returns registry records, newest first. The state route returns the
whole `ProjectState` document, not a wrapper.

### Register media

```http
POST /api/v1/projects/{project_id}/media
```

```json
{ "file_path": "/media/raw.mp4" }
```

The worker probes the file with FFprobe, persists `MediaInfo`, and invalidates
derived results: PCM/VAD spans, transcript, culls, overrides, timeline
segments, and vertical clips. It returns `media`, the updated `state`, and the
project record. Unreadable files return `422 media_not_found`; paths outside the
allowlist return `403 path_not_allowed`.

## 5. Module and run routes

```http
PUT  /api/v1/projects/{project_id}/modules/{module_id}/config
PUT  /api/v1/projects/{project_id}/modules/{module_id}/enabled
POST /api/v1/projects/{project_id}/modules/{module_id}/run
POST /api/v1/projects/{project_id}/run
```

`module_id` is one of `ingest`, `vad`, `transcribe`, `retakes`, `jl_cuts`,
`zooms`, `shorts`, or `export`. Unknown ids return `404 unknown_module`.

### Config

The config body is a partial module config. It is merged over the current
config and validated with the same Pydantic model used by the domain:

```json
{ "punch_in_scale": 1.25 }
```

Unknown fields and out-of-range values return `422 invalid_config`. A config
change clears cached hashes; it does not delete timeline results, because the
next full run recomputes them.

### Enabled

```json
{ "enabled": false }
```

The flag is persisted in `module_enabled` and consumed by the next project run.

### Run a module

Per-module reruns are not implemented in 0.21.2. The route validates the
project and module id, then returns:

```json
{
  "detail": {
    "ok": false,
    "code": "not_implemented",
    "message": "Per-module reruns are not implemented in this build. Run the full project pipeline instead.",
    "capability": "module_run"
  }
}
```

### Run the project

```http
POST /api/v1/projects/{project_id}/run
```

```json
{ "run_upstream": false, "force": false }
```

Returns `202` with the same job envelope as `POST /api/v1/jobs`. The project
run preserves:

- `project_id` and the next state `revision`;
- `modules_config` and `module_enabled`;
- the persisted transcript, including word timings;
- manual sentence overrides;
- the configured export targets and FCPXML dialect.

The portable engine honors the enabled flags for transcribe, retakes, J/L cuts,
zooms, shorts, and export. `ingest` and `vad` are required; disabling either
returns `409 module_bypassed`. A project without registered media returns
`409 media_not_registered`. Shorts without a transcript require the transcribe
module; otherwise the route returns `422 transcript_required`.

After the worker writes state, the API records the revision snapshot. A project
may have only one active job; a second start returns `409 job_already_running`.

### Cancel

```http
POST /api/v1/projects/{project_id}/cancel
```

Cancels the active project job cooperatively. If no job is active, returns
`404 job_not_found`.

### Events

```http
GET /api/v1/projects/{project_id}/events
Accept: text/event-stream
```

Streams the active or most recent job for the project. The payload and close
behavior match the job events route. Projects with no job return
`404 job_not_found`.

## 6. Transcript, export, and preset routes

### Transcript

```http
GET /api/v1/projects/{project_id}/transcript?include_word_timestamps=true
```

```json
{
  "ok": true,
  "project_id": "8d1d4f0e-...",
  "revision": 3,
  "sample_rate": 48000,
  "sentence_count": 2,
  "transcript": [
    {
      "id": 0,
      "start_sample": 0,
      "end_sample": 48000,
      "text": "Welcome back.",
      "words": []
    }
  ],
  "srt": "1\n00:00:00,000 --> 00:00:01,000\nWelcome back.\n"
}
```

Projects without a transcript return `404 transcript_not_found`.

### Overrides

```http
PATCH /api/v1/projects/{project_id}/transcript/overrides
```

```json
{
  "overrides": [
    { "sentence_id": 4, "action": "keep" },
    { "sentence_id": 7, "action": "discard" }
  ]
}
```

Overrides replace the whole set atomically, clear retake culls/guard restores,
and invalidate timeline and vertical results. Unknown sentence ids return
`422 invalid_override`.

Word-level retakes are not supported yet. A request with `word_index` returns
`422 word_overrides_not_supported`; sentence-level culling remains the
authoritative behavior.

### Export

```http
POST /api/v1/projects/{project_id}/exports
```

```json
{ "targets": ["resolve", "premiere"], "dialect": "1.10" }
```

Both fields are optional. Without `targets`, the export flags in
`modules_config.export` choose the artifacts. Paths stay under
`.videoflow/exports/`. A project without timeline segments returns
`409 state_not_ready`.

### Presets

```http
GET  /api/v1/presets
GET  /api/v1/presets/{name}
PUT  /api/v1/presets/{name}
POST /api/v1/projects/{project_id}/presets/{name}/apply
```

Preset names match `[a-z0-9][a-z0-9-]{0,63}`. `PUT` writes an operator preset
under `$VIDEOWFLOW_HOME/presets/{name}.json`; the file keeps partial keys so
new defaults still apply later. Operator files shadow shipped presets with the
same name. Invalid names return `422 invalid_preset_name`; invalid configs
return `422 preset_invalid`.

`GET /api/v1/presets` returns full resolved configs plus a `source` of
`shipped` or `operator`. Applying a preset replaces the project's module config
and enabled flags atomically and increments the project revision.

## 7. Security

- The server binds to loopback.
- Every HTTP path is resolved and checked before the worker starts.
- The UI origin allowlist is the local dev server.
- Do not expose the port. v1 has no authentication.
