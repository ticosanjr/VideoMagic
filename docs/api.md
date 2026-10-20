# HTTP API

Base URL: `http://127.0.0.1:8765`. No authentication in v1. Bind only to
loopback.

Implemented today:

- `GET /health`
- `GET /api/v1/system`
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
| 403 | `path_not_allowed` |
| 404 | `job_not_found`, `project_not_found`, `preset_not_found`, `unknown_module`, `transcript_not_found` |
| 409 | `job_already_running`, `module_bypassed`, `media_not_registered`, `state_not_ready` |
| 422 | validation, `invalid_time`, `media_not_found`, `transcript_required`, `invalid_override`, `word_overrides_not_supported`, `invalid_config`, `invalid_preset_name`, `preset_invalid`, `export_failed` |
| 429 | `job_queue_full` |
| 500 | `project_state_invalid` |
| 501 | `not_implemented` (per-module reruns) |

## 2. Health and system

```http
GET /health
```

```json
{ "status": "ok", "service": "videoflow", "version": "0.17.0" }
```

```http
GET /api/v1/system
```

```json
{
  "ok": true,
  "version": "0.17.0",
  "home": "/home/editor/.videoflow",
  "allowed_roots": ["/home/editor", "/home/editor/projects", "/home/editor/.videoflow"],
  "ffmpeg": "/usr/bin/ffmpeg",
  "ffprobe": "/usr/bin/ffprobe"
}
```

`allowed_roots` comes from `VIDEOWFLOW_ALLOWED_ROOTS` (path-separator list) or
defaults to home, cwd, and the portable data directory.

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
  "jcut": true,
  "lcut": false,
  "offset_ms": 200,
  "crossfade_ms": 20,
  "handle_check": true,
  "zooms": true,
  "zoom_mode": "alternate_cuts",
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
  "shorts_min_sec": 30,
  "shorts_max_sec": 60,
  "shorts_subtitles": true,
  "overrides": [
    { "sentence_id": 4, "action": "keep" },
    { "sentence_id": 7, "action": "discard" }
  ],
  "transcribe": true,
  "asr_base_url": "http://localhost:8000/v1",
  "asr_model": "whisper-1",
  "asr_language": "pt",
  "whisper_model": null
}
```

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
`VIDEOWFLOW_ASR_BASE_URL`. With no URL, the bundled whisper.cpp CLI and tiny
model run locally. An empty `whisper_model` uses the bundled model; a path
selects a larger GGML file. SRT wins if present.

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
  "version": "0.17.0",
  "speech_interval_count": 3,
  "video_segment_count": 3,
  "audio_segment_count": 3,
  "warnings": [],
  "artifacts": {
    "resolve": "/projects/interview-edit/exports/timeline.fcpxml",
    "premiere": "/projects/interview-edit/exports/timeline.xml",
    "kdenlive": "/projects/interview-edit/exports/timeline.otio"
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

Per-module reruns are not implemented in 0.17.0. The route validates the
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
