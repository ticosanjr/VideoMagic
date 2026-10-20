# HTTP API

Base URL: `http://127.0.0.1:8765`. No authentication in v1. Bind only to
loopback.

Implemented today:

- `GET /health`
- `GET /api/v1/system`
- `POST /api/v1/jobs`, `GET /api/v1/jobs`, `GET /api/v1/jobs/{id}`,
  `POST /api/v1/jobs/{id}/cancel`, `GET /api/v1/jobs/{id}/events`
- `GET /mcp/` (MCP Streamable HTTP) and `GET /` (rack UI when built)

Project-scoped routes and transcript routes are specified below but not
implemented yet.

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
| 404 | `job_not_found` |
| 409 | `upstream_dirty`, `module_bypassed` |
| 422 | validation, `invalid_time` |
| 429 | `job_queue_full` |
| 501 | `not_implemented` (future routes) |

## 2. Health and system

```http
GET /health
```

```json
{ "status": "ok", "service": "videoflow", "version": "0.10.0" }
```

```http
GET /api/v1/system
```

```json
{
  "ok": true,
  "version": "0.10.0",
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
  "jcut": true,
  "lcut": false,
  "zooms": true,
  "dialect": "1.9",
  "transcript": "/media/interview.srt",
  "cull_retakes": true
}
```

`transcript` is optional and is resolved through the same allowlist as media.
When `cull_retakes` is true and `VIDEOWFLOW_LLM_BASE_URL` is set, the worker
uses the OpenAI-compatible endpoint; otherwise only exact repeated text is
culled.

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
    "created_at": "2026-10-19T21:09:48+00:00",
    "started_at": "2026-10-19T21:09:48+00:00",
    "finished_at": null
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

### State

```http
GET /api/v1/jobs/{job_id}/state
```

Returns the `project_state.json` written by the job. The UI uses it for the
inspector (transcript sentences, culls, guard restorations). If the job has not
written state yet, the route returns `404 state_not_found`.

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
  "version": "0.10.0",
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

## 4. Planned project routes

These are the contract for the neural pass. They return 404 today.

### Create

```http
POST /api/v1/projects
```

```json
{ "root": "/home/editor/projects/interview" }
```

Creates `.videoflow/`, writes state revision 1, returns the whole document.

### Read

```http
GET /api/v1/projects/{project_id}/state
```

### Register media

```http
POST /api/v1/projects/{project_id}/media
```

```json
{ "file_path": "/media/raw.mp4" }
```

Returns `MediaInfo`; rejects paths outside the allowlist.

## 5. Planned module routes

```http
PUT  /api/v1/projects/{project_id}/modules/{module_id}/config
PUT  /api/v1/projects/{project_id}/modules/{module_id}/enabled
POST /api/v1/projects/{project_id}/modules/{module_id}/run
POST /api/v1/projects/{project_id}/run
```

`run` accepts `{"run_upstream": false, "force": false}` and returns
`409 upstream_dirty` or `409 module_bypassed` when the rack rules refuse.

## 6. Planned transcript and export routes

```http
GET   /api/v1/projects/{project_id}/transcript?include_word_timestamps=true
PATCH /api/v1/projects/{project_id}/transcript/overrides
POST  /api/v1/projects/{project_id}/exports
GET   /api/v1/presets
GET   /api/v1/presets/{name}
PUT   /api/v1/presets/{name}
```

Overrides replace the set atomically and invalidate retakes and downstream
modules. Export paths stay under `.videoflow/exports/`.

## 7. Security

- The server binds to loopback.
- Every HTTP path is resolved and checked before the worker starts.
- The UI origin allowlist is the local dev server.
- Do not expose the port. v1 has no authentication.
