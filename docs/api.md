# HTTP API

Base URL: `http://127.0.0.1:8765`. No authentication in v1. Bind only to
loopback.

Implemented today:

- `GET /health`
- `GET /api/v1/system`
- `GET /api/v1/capabilities`
- `GET /api/v1/steps`, `GET /api/v1/recipes`, `GET /api/v1/recipes/{id}`,
  `PUT /api/v1/recipes/{id}`, `POST /api/v1/recipes/validate`,
  `POST /api/v1/recipes/preflight`, `POST /api/v1/recipes/run`,
  `POST /api/v1/steps/{step_id}/run`
- `POST /api/v1/batches`, `GET /api/v1/batches`,
  `GET /api/v1/batches/{id}`, `POST /api/v1/batches/{id}/cancel`
- `GET /api/v1/runs?output=...&limit=...&offset=...` returns paginated run history
- `GET /api/v1/jobs?limit=...&offset=...&summary=true` and
  `/api/v1/batches?limit=...&offset=...` paginate persisted jobs/batches.
  `summary=true` omits the embedded recipe document from every job.
- `POST /api/v1/exports/validate` checks FCPXML, XMEML, and Kdenlive structure
- `POST /api/v1/maintenance/prune` trims output checkpoints, B-roll cache, run
  history, old preview frames, legacy preview intermediates, and render
  segments
- `GET /api/v1/fs/roots`, `GET /api/v1/fs/list`, `POST /api/v1/fs/mkdir`
- `GET /api/v1/media/probe`
- `POST /api/v1/media/import`
- `GET/PUT/DELETE /api/v1/publish/targets`, `GET /api/v1/publish/queue`,
  `POST /api/v1/publish/dispatch`, `POST /api/v1/jobs/{id}/shorts/{index}/publish`
- `GET /api/v1/assets/sfx`, `POST /api/v1/assets/sfx?name=`,
  `DELETE /api/v1/assets/sfx/{name}`
- `GET /api/v1/assets/fonts`, `POST /api/v1/assets/fonts`
- `GET /api/v1/assets/images`, `POST /api/v1/assets/images`
- `GET /api/v1/assets/music`, `POST /api/v1/assets/music`
- `GET/PUT/DELETE /api/v1/brand-templates`, `POST /api/v1/brand-templates/{name}/apply`
- `GET/PUT/DELETE /api/v1/project-templates`, `POST /api/v1/project-templates/{name}/apply`
- `POST /api/v1/config/export`, `POST /api/v1/config/import`
- Short thumbnail generation and download
- `POST /api/v1/recipes/run`, `GET /api/v1/jobs`, `GET /api/v1/jobs/{id}`,
  `POST /api/v1/jobs/{id}/cancel`, `POST /api/v1/jobs/cancel_all`,
  `POST /api/v1/jobs/pause_all`, `POST /api/v1/jobs/resume_all`,
  `POST /api/v1/jobs/{id}/pause`, `POST /api/v1/jobs/{id}/unpause`,
  `POST /api/v1/jobs/{id}/retry`, `GET /api/v1/jobs/{id}/events`
- `GET /api/v1/jobs/{id}/interactions`,
  `POST /api/v1/jobs/{id}/interactions/{interaction_id}/respond`,
  `POST /api/v1/hilt/approve`,
  `POST /api/v1/jobs/{id}/interactions/{interaction_id}/files`,
  `GET /api/v1/hilt/pending`, `GET /api/v1/hilt/channels`,
  `POST /api/v1/hilt/test`, `POST /api/v1/hilt/slack/events`,
  `POST /api/v1/hilt/email/inbound` ([hilt.md](hilt.md))
- `GET /api/v1/presets`, `GET /api/v1/presets/{name}`,
  `PUT /api/v1/presets/{name}`
- `GET /mcp/` (MCP Streamable HTTP) and `GET /` (recipe studio UI when built)

Recipe runs are the only project-producing path. Timeline edits operate on the
canonical `project_state.json` and preserve undo/redo history.

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
| 501 | `not_implemented` for capabilities not present in this build |

## 2. Health and system

```http
GET /health
```

```json
{ "status": "ok", "service": "videoflow", "version": "2.0.0" }
```

```http
GET /api/v1/system
```

```json
{
  "ok": true,
  "version": "2.0.0",
  "home": "/home/editor/.videoflow",
  "allowed_roots": ["/home/editor", "/home/editor/projects", "/home/editor/.videoflow"],
  "ffmpeg": "/usr/bin/ffmpeg",
  "ffprobe": "/usr/bin/ffprobe",
  "settings_error": "",
  "database_error": ""
}
```

`settings_error` is non-empty when `settings.json` could not be parsed and the
server fell back to defaults. `database_error` reports the last SQLite failure.
Both also appear in the doctor checks. `allowed_roots` comes from `VIDEOWFLOW_ALLOWED_ROOTS` (path-separator list) or
defaults to home, cwd, and the portable data directory.

### Capabilities and provider policy

```http
GET /api/v1/capabilities?allow_external=true
```

Returns feature availability plus the effective external-service policy. A
blocked provider includes a reason string. `VIDEOWFLOW_ALLOW_EXTERNAL=0` is a
global kill switch; localhost providers remain available.

### Analyze a Short

```http
POST /api/v1/jobs/{job_id}/shorts/{index}/analyze
```

Returns audio features/label, visual motion, optional face statistics, and
caveats. Results are stored under `short.analysis`.

### Publishing

```http
PUT /api/v1/publish/targets/studio
POST /api/v1/jobs/{job_id}/shorts/{index}/publish
GET /api/v1/publish/queue
```

Targets are webhook URLs with a secret-name reference. Scheduled items are sent
by the local daemon, or manually via `POST /api/v1/publish/dispatch`.

### URL import

```http
POST /api/v1/media/import
Content-Type: application/json
```

```json
{
  "url": "https://example.com/video",
  "max_height": 1080,
  "allow_playlist": false,
  "allow_external_services": true
}
```

Downloads into `<home>/downloads` with yt-dlp and returns the local path plus
probe metadata. Host allowlists and the global external kill switch apply.

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

Jobs are created by `POST /api/v1/recipes/run` (or
`POST /api/v1/recipes/{recipe_id}/run` via the step runner). The legacy
`POST /api/v1/jobs` creation route and its flat 127-field option object were
removed in 2.59.4; use a recipe with typed variables and step parameters.

```http
POST /api/v1/recipes/run
Content-Type: application/json

{"recipe_id": "youtube_talking_head",
 "source": "/media/interview.mp4",
 "output": "/projects/interview-edit"}
```

The default concurrency is two active jobs per process. A third start returns
`429 job_queue_full` unless it is queued.

`POST /api/v1/recipes/run` accepts an optional `idempotency_key`. While a job
with that key is queued, running, or waiting for approval, a second request
returns the same job instead of creating another one. Once the job reaches a
terminal status the key is free again.

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

Cancellation is cooperative between stages and immediate inside a stage: the
render and preview adapters pass a cancel event to FFmpeg, which runs in its own
process group. On cancel or timeout the adapter sends `SIGTERM`, waits one
second, then sends `SIGKILL`, and the queue removes the partial file. A
`kill -9` of the service leaves no orphaned FFmpeg process.

Use `POST .../cancel?force=true` to mark a running job cancelled immediately and
drain the next queued worker. `DELETE /api/v1/jobs/{job_id}` removes a job from
the queue, store, and Activity list; add `?force=true` to stop and remove a
running job. `POST /api/v1/jobs/cancel_all?force=true` stops every active job and
drains the queue. Cancelling or removing a queued job also drains the next
worker.

### Pause, resume, priority

`POST /api/v1/jobs/{id}/pause` pauses a queued job immediately or requests a
cooperative pause for a running one. `POST .../unpause` requeues it.
`PATCH .../priority` with `{"priority": -10..10}` stores the value and reorders
the pending queue.

### Retry

```http
POST /api/v1/jobs/{job_id}/retry
```

Accepts `failed` and `cancelled` jobs. It re-enqueues the original source,
output, and options with `resume: true` and returns `202` with the new job.
Any other status returns `409 state_not_ready`; an unknown id returns `404`.

```json
{ "ok": true, "job": { "job_id": "…", "status": "queued", "options": { "resume": true } } }
```

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

### Project templates and config I/O

```http
GET/PUT/DELETE /api/v1/project-templates[/{name}]
POST /api/v1/project-templates/{name}/apply
POST /api/v1/config/export
POST /api/v1/config/import
```

Templates store non-secret flat job options. Config envelopes are versioned and
strip source/output/transcript/project fields.

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

`target` is the artifact key from `job.result.artifacts` (for example `mp4`,
`resolve`, `premiere`, `kdenlive`, or a plan such as `motion_scenes`). The file
must live under the job's output directory. Unknown targets return
`404 artifact_not_found`; a path outside the output returns
`403 artifact_not_allowed`.

### Edit a plan artifact

```http
PATCH /api/v1/jobs/{job_id}/artifacts/{target}
{"payload": {"scenes": []}}
```

Editable keys are `motion_scenes`, `motion_callouts`, `storyboard_units`,
`script_json`, and `style_guide`. The payload is written atomically to the
existing artifact inside the job output, and every edit is appended to
`plan-edits.jsonl`. Edits change the plan only; re-run the affected step or
render to update the media. Non-editable keys return
`422 artifact_not_editable`, invalid shapes return `422 artifact_invalid`, and
missing files return `404 artifact_not_found`.

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

On success, `job.result` is the recipe run report:

```json
{
  "ok": true,
  "version": "2.0.0",
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

## 4. Recipe, timeline, and provider routes

The legacy project store, module rack routes, and per-module reruns are gone.
Project state is created by recipe runs and edited through the job timeline API.

- `POST /api/v1/recipes/run`, `POST /api/v1/recipes/run/{step_id}`,
  `POST /api/v1/recipes/dry-run`
- `POST /api/v1/jobs/{job_id}/resume`
- `GET /api/v1/plugins` (plugins plus registered panels),
  `POST /api/v1/plugins/reload`,
  `POST /api/v1/plugins/{id}/enable`
- `GET /api/v1/system/metrics`, `GET /api/v1/system/backup`
- `GET /api/v1/jobs/{job_id}/timeline`, `PATCH /api/v1/jobs/{job_id}/timeline`
- `POST /api/v1/jobs/{job_id}/timeline/undo`,
  `POST /api/v1/jobs/{job_id}/timeline/redo`
- `GET /api/v1/jobs/{job_id}/timeline/waveform` for normalised peaks
- `PATCH /api/v1/jobs/{job_id}/timeline/batch` for atomic multi-clip edits
- `PATCH /api/v1/jobs/{job_id}/timeline/clip/{clip_id}` for transitions,
  scale, position, and audio fades
- `PATCH /api/v1/jobs/{job_id}/timeline/clips` applies the same style to many
  clips in one revision and one undo entry
- `GET/PUT /api/v1/jobs/{job_id}/timeline/meta`,
  `POST /api/v1/jobs/{job_id}/timeline/markers`,
  `DELETE /api/v1/jobs/{job_id}/timeline/markers/{id}`,
  `PUT /api/v1/jobs/{job_id}/timeline/tracks/{track}`
- `GET/PATCH /api/v1/jobs/{job_id}/broll`
- `GET/PATCH /api/v1/jobs/{job_id}/review`,
  `GET/POST /api/v1/jobs/{job_id}/review/comments`
- `GET /api/v1/jobs/{job_id}/thumbnails`,
  `POST /api/v1/jobs/{job_id}/thumbnails/select`,
  `GET /api/v1/jobs/{job_id}/thumbnails/metrics`,
  `POST /api/v1/jobs/{job_id}/thumbnails/{name}/metric`,
  `GET /api/v1/jobs/{job_id}/thumbnails/{name}`
- `GET /api/v1/schedules`, `PUT/DELETE /api/v1/schedules/{id}`,
  `POST /api/v1/schedules/{id}/run`
- `POST /api/v1/jobs/{job_id}/render`,
  `GET /api/v1/jobs/{job_id}/render/status`,
  `POST /api/v1/jobs/{job_id}/render/cancel`,
  `GET /api/v1/jobs/{job_id}/render/file`
- `POST/DELETE /api/v1/providers/{id}/secret`
- `PATCH /api/v1/jobs/{job_id}/broll/undo|redo`
- `POST/GET /api/v1/jobs/{job_id}/preview`,
  `GET /api/v1/jobs/{job_id}/preview/status`,
  `POST /api/v1/jobs/{job_id}/preview/cancel`,
  `GET /api/v1/jobs/{job_id}/preview/file`
- `GET/PUT /api/v1/settings`, `POST /api/v1/settings/reset`,
  `GET /api/v1/settings/export`, `POST /api/v1/settings/import`
- `GET /api/v1/system/doctor`, `GET /api/v1/system/support-bundle`
- `GET/PUT/DELETE /api/v1/services/definitions`,
  `POST /api/v1/services/definitions/{id}/start|stop`,
  `GET /api/v1/services/definitions/{id}/status|logs`
- `POST /api/v1/models/local`, `POST /api/v1/models/{id}/verify`
- `GET /api/v1/providers`, `PUT /api/v1/providers/{id}`,
  `DELETE /api/v1/providers/{id}`,
  `POST /api/v1/providers/{id}/default`,
  `GET /api/v1/providers/resolve?capability=llm`
- `GET /api/v1/models/downloads`, `POST /api/v1/models/{id}/download`,
  `DELETE /api/v1/models/downloads/{id}`
- `GET /api/v1/presets`, `GET /api/v1/presets/{name}`,
  `PUT /api/v1/presets/{name}`

`PATCH /api/v1/jobs/{job_id}/timeline` accepts `trim`, `move`, `delete`,
`split`, `ripple`, `ripple_trim`, `slip`, `slide`, `duplicate`, `deactivate`,
`activate`, and `recut`. Deactivation moves a clip into `inactive_segments`
instead of destroying it. `recut` takes an inactive id plus new source
`start_sec`/`end_sec`, resizes the neighboring active clips, and keeps the
active timeline packed. Recut recipes also populate `inactive_segments`
automatically from VAD silence and retake culling; timeline edits are only
needed for manual corrections. Every edit validates against the
source media, records one undo entry in `timeline_history.json`, increments
`revision`, and returns a warning that rendered artifacts must be refreshed.

`slip` shifts the source range without moving the clip on the timeline:

```json
{ "clip_id": "c1", "action": "slip", "delta_sec": 0.4 }
```

`ripple_trim` trims the clip and moves every following clip by the same delta.
`PATCH .../timeline/batch` accepts the same actions for atomic multi-clip edits,
which is how the UI applies a group trim.

When `timeline_meta.json` marks the video or audio track as `locked`, clip edits
return `409 state_not_ready`. The `muted` audio track makes render and preview
append `volume=0`; `solo` overrides mute.

### Clip comments

```http
GET    /api/v1/jobs/{job_id}/timeline/comments?clip_id=v1
POST   /api/v1/jobs/{job_id}/timeline/comments
DELETE /api/v1/jobs/{job_id}/timeline/comments/{comment_id}
```

Comments live in `timeline_meta.json` with `id`, `clip_id`, `text`, `author`,
and `created_at`.

### Copilot

```http
POST /api/v1/copilot/recipe
POST /api/v1/jobs/{job_id}/copilot/timeline
```

The recipe endpoint returns a validated recipe draft. The timeline endpoint
returns proposed edits and, with `"apply": true`, applies them with one undo
entry. Unknown clip ids or actions are rejected before writing. See
[integrations.md](integrations.md) for OpenCode/Paperclip and DeepSeek setup.

### Cost metrics

```http
GET /api/v1/metrics/cost
```

Returns call and prompt/completion token totals, globally and per model, from
the OpenAI-compatible LLM client.

### Waveform peaks

```http
GET /api/v1/jobs/{job_id}/timeline/waveform?start=0&end=12.5&buckets=600
```

Returns normalised RMS peaks for a timeline range. The source is decoded once
at 4 kHz mono, sampled into 50 ms buckets, and cached under
`<home>/waveforms/<digest>.json`; later calls only slice and resample the cache.
The response includes `peaks`, `bucket_sec`, `start_sec`, and `end_sec`.
Missing source media returns `409 state_not_ready`; a decode failure returns
`422 waveform_failed`.

```json
{
  "clip_id": "c1",
  "action": "split",
  "split_sec": 12.5
}
```

B-roll approvals live in `broll_approval.json` inside the job output. The
Shorts renderer consumes every approved entry, in the saved order.

`POST /preview?background=true` starts a worker and returns immediately. Poll
`/preview/status` for progress and call `/preview/cancel` to stop. Previews apply
`titles.ass`, `color/filters.json`, and `audio/master-filters.json` when present.

Render and preview outputs carry a manifest keyed by the project state, filter
files, titles, and proxy height. `/render/status` and `/preview/status` only
return `ready` while that manifest matches; otherwise they report `idle` or
`stale`, and the file endpoints refuse a non-current file. A render or preview
that finishes after the timeline changed is never reported as current.

Settings are stored in `$VIDEOWFLOW_HOME/settings.json`. Runtime/path changes are
marked restart-required. Service definitions are stored in `videoflow.db`.
Local models are registered in `models-local.json`. The support bundle is a ZIP
with doctor output, settings, redacted environment, providers, models, service
definitions, and the server log.

Schedules are stored in SQLite (`videoflow.db`) with a one-time migration from
`recipe-schedules.json`. Review decisions live in `review_approval.json`;
comments in `review_comments.json`; thumbnail selection in
`thumbnail_choice.json`; metrics in `thumbnail_metrics.json`.

Secrets are read from the environment, OS keyring, or a 0600 `secrets.json`
fallback. The API only reports presence.

`transcript.translate` uses the recipe LLM provider and writes
`translation/translated.json` plus an SRT. `audio.qa` writes
`audio/qa.json` with EBU R128 integrated loudness and true peak. NLE exports
include a `sidecars/` folder with titles, color filters, audio-master filters,
B-roll, markers, and `sidecars.json`.

Provider configuration lives in `$VIDEOWFLOW_HOME/providers.json`. Secrets are
never stored; `api_key_env` names an environment variable. `resolve` returns
the enabled default followed by its fallback chain.

## 7. Security

- The server binds to loopback.
- Every HTTP path is resolved and checked before the worker starts.
- The UI origin allowlist is the local dev server.
- Do not expose the port. v1 has no authentication.

## 7.1 Timeline versions

- `GET /api/v1/timelines` lists saved timeline snapshots.
- `POST /api/v1/jobs/{id}/timeline/snapshots` with `{"name": "..."}` saves the
  current state.
- `POST /api/v1/timelines/{snapshot_id}/load` with `{"job_id": "..."}` replaces
  the job timeline, increments revision, and records undo.
- `GET /api/v1/timelines/{snapshot_id}/file` downloads the timeline JSON.
- `POST /api/v1/timelines/import` imports `{"payload": {...}, "name": "..."}`.
- `DELETE /api/v1/timelines/{snapshot_id}` removes a saved version.

## 8. Timeline concurrency (ETag)

`GET /api/v1/jobs/{id}/timeline` returns `ETag: "timeline-<revision>"`, the
active `video`/`audio` lanes, `source_duration_sec`, `inactive` source ranges,
overlay records, structured `titles` cues, `live_eligible`/`live_reason`, and a
`live_source` status. When the original codec is browser-safe,
`GET /api/v1/jobs/{id}/source/file` serves it with HTTP Range. Otherwise
`POST /api/v1/jobs/{id}/live-source` builds a cached H.264/AAC proxy;
`GET /api/v1/jobs/{id}/live-source/status` reports `missing|preparing|ready|failed`
and `GET /api/v1/jobs/{id}/live-source/file` serves the proxy with Range.
`GET /api/v1/jobs/{id}/overlays/{overlay_id}/file` serves overlay assets.
Crossfades, fade-to-black, overlays, structured titles, and track mute/solo
compose in-browser; FFmpeg filters and clip transforms fall back to the
rendered preview.

- Send `If-None-Match` to get `304` when nothing changed.
- Send `If-Match` with the last ETag on `PATCH /timeline`,
  `PATCH /timeline/clip/{clip_id}`, `PATCH /timeline/clips`, and
  `PATCH /timeline/batch`. The UI does this and reloads on `412` instead of
  overwriting another window.
- A stale value returns `412` with `code: "precondition_failed"` and a fresh
  ETag in `details.etag`; nothing is written.

## 10. Assistant

| Method | Path | Purpose |
| --- | --- | --- |
| POST | `/api/v1/jobs/{id}/assistant` | Plan with `{prompt}`; read-only tools run automatically |
| POST | `/api/v1/jobs/{id}/assistant/approve` | Apply `{approval_id}` exactly once |
| GET | `/api/v1/jobs/{id}/assistant/history` | Last 50 turns |

Response fields: `message`, `actions`, `observations`, `diff`,
`requires_approval`, `approval_id`, `tokens`, `cost_usd`, `budget_usd`,
`remaining_usd`. A turn with writes never mutates the timeline; approvals do.

## 11. Runs and variants

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/jobs/{id}/dag` | Nodes, edges, status, durations, p50/p95, retry policy |
| GET | `/api/v1/jobs/{id}/variants` | Recipe variants, Shorts, thumbnails, winner |
| POST | `/api/v1/jobs/{id}/variants/select` | Persist `{name}` as winner |
| GET | `/api/v1/jobs/{id}/logs?module=&level=&limit=` | Filtered logs; `download=true` |
| GET | `/api/v1/jobs/{id}/frame?time=&height=` | Cached JPEG frame per revision |

## 12. Contracts and errors

- OpenAPI: `/openapi.json`, `/docs`.
- Error catalog: [errors.md](errors.md).
- Every mutation documents `403/404/409/412/422/429/500` with the
  `ErrorEnvelope` schema.
- MCP behavior annotations are documented in [mcp.md](mcp.md).
