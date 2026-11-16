# Data model

The committed JSON Schemas in `schemas/` are generated from the Pydantic models
by `scripts/export_schemas.py`. A test fails if they drift.

| Schema | Model | Purpose |
| --- | --- | --- |
| `project-state.schema.json` | `ProjectState` | The document at `.videoflow/project_state.json` |
| `preset.schema.json` | `Preset` | Preset files in `~/.videoflow/presets/` |
| `llm-retake-response.schema.json` | `LlmRetakeResponse` | The only accepted retake payload |
| `api-error.schema.json` | `ApiError` | REST and MCP error body |
| `job-record.schema.json` | `JobRecord` | Job status for the API and MCP |

## 1. Project state

```json
{
  "schema_version": 2,
  "project_id": "8d1d4f0e-...",
  "revision": 1,
  "primary_source_id": "primary",
  "sources": {
    "primary": {
    "source_path": "/media/raw.mp4",
    "duration_frames": 21614,
    "fps_num": 30000,
    "fps_den": 1001,
    "width": 3840,
    "height": 2160,
      "audio_sample_rate": 48000,
      "start_timecode_frames": 0
    }
  },
  "source_offsets": {},
  "media_info": {
    "source_path": "/media/raw.mp4",
    "duration_frames": 21614,
    "fps_num": 30000,
    "fps_den": 1001,
    "width": 3840,
    "height": 2160,
    "audio_sample_rate": 48000,
    "start_timecode_frames": 0
  },
  "modules_config": { "providers": {}, "ingest": {}, "vad": {},
                      "transcribe": {}, "retakes": {}, "jl_cuts": {}, "zooms": {},
                      "shorts": {}, "export": {} },
  "module_enabled": { "ingest": true, "vad": true, "transcribe": true,
                      "retakes": true, "jl_cuts": true, "zooms": true,
                      "shorts": true, "export": true },
  "cache_hashes": { "ingest": "…", "vad": "…" },
  "vad_intervals": [{ "start_sample": 48000, "end_sample": 96000 }],
  "transcript": [
    {
      "id": 1,
      "start_sample": 48000,
      "end_sample": 96000,
      "text": "Welcome back.",
      "words": [
        { "word": "Welcome", "start_sample": 48000, "end_sample": 58000, "probability": 0.98 }
      ]
    }
  ],
  "retake_culls": [4, 5],
  "retake_guard_restores": [5],
  "manual_overrides": [{ "sentence_id": 7, "word_index": null, "action": "discard" }],
  "video_segments": [
    {
      "clip_id": "c1",
      "source_id": "primary",
      "source_in_frame": 30,
      "source_out_frame": 210,
      "timeline_in_frame": 0,
      "timeline_out_frame": 180,
      "transform": { "scale": 1.15, "pos_x": 0, "pos_y": 0, "type": "punch_in",
                     "anchor": "upper_third", "pan_direction": "none" }
    }
  ],
  "audio_segments": [
    {
      "clip_id": "c1",
      "source_id": "primary",
      "source_in_sample": 48000,
      "source_out_sample": 336000,
      "timeline_in_sample": 0,
      "timeline_out_sample": 288000,
      "fade_in_samples": 960,
      "fade_out_samples": 960,
      "fade_curve": "logarithmic"
    }
  ],
  "vertical_clips": [
    {
      "clip_id": "v1",
      "title": "The hook",
      "start_sample": 5760000,
      "end_sample": 8000000,
      "crop_focus_x": 0.5,
      "reframe_mode": "center_crop_9_16"
    }
  ]
}
```

### Invariants

- `schema_version` is `2`. Version 1 states are migrated by adding a
  `primary` source and a `source_id` on every segment.
- `sources` stores real media per `source_id`; `primary_source_id` selects the
  timeline/output timebase.
- `revision` starts at `1` and increases on every accepted write. The matching
  snapshot lives at `.videoflow/revisions/000001.json`, `000002.json`, and so on.
- Sentence ids are unique within a transcript.
- Every span is half-open, `[start, end)`, in its declared unit.
- `video_segments` and `audio_segments` may disagree in range. They share a
  `clip_id`; that disagreement is what makes a J-cut possible.
- Culls and manual overrides are decisions, not deleted transcript rows. The
  transcript is never mutated by a cull.
- `retake_guard_restores` records sentences the guard saved from an illegal
  model discard.
- Every time field is an integer. There is no `duration_sec` field.

### Precedence

```
manual keep/discard
  > retake guard
  > LLM discard
  > VAD keep
```

## 2. Configuration

All config models forbid unknown fields. That is deliberate: a request containing
`api_key` is rejected instead of silently stored.

| Model | Notable validation |
| --- | --- |
| `IngestConfig` | booleans only |
| `VadConfig` | engine `auto`/`silero`/`ffmpeg`, threshold 0.1–0.9, non-negative durations |
| Speech settings | profile (`balanced` default), engine, model, language, device, compute type, beam, CPU threads, word timestamps, VAD, remote ASR endpoint | See [asr.md](asr.md) |
| `RetakesConfig` | no secret value; `secret_name` only; temperature fixed at 0 |
| `JlCutsConfig` | offset 100–500 ms, crossfade 10–50 ms |
| `ZoomsConfig` | scale 1.05–1.30 |
| `ShortsConfig` | min ≤ max; 1–20 clips; prompt/reprompt; hook modes; audio-energy and scene boosts; reframe center/motion/face; filler list; aspect 9:16/1:1/16:9; source end > start |
| `ProvidersConfig` | external services opt-in; optional remote-host allowlist |
| `AudioEnhanceConfig` | opt-in high-pass, denoise, and loudnorm for rendered Shorts |
| `OverlayConfig` | watermark asset, position, margin, width ratio, opacity |
| `MusicConfig` | music asset, volume, ducking, fades |
| `TtsConfig` | provider, base URL, model, voice, speed, volume, original volume; secret name only |
| `IntroOutroConfig` | image assets and 0.2–10 s card durations |
| `DubbingConfig` | target language and original volume |
| `PublishTarget` | webhook URL, secret name, enabled |
| `PublishQueueItem` | asset, metadata, schedule, status, attempts |
| `ShortClip.analysis` | audio labels, motion, optional face statistics |
| `BrandTemplate` | caption style, overlay, music, and intro/outro bundle |
| `CaptionStyle.censor_*` | optional profanity word list and replacement |
| `CaptionStyle` branding | keyword list/color, emoji map, brand vocabulary |
| `ExportConfig` | dialect 1.9/1.10, write flags |

## 3. Presets

```json
{
  "name": "youtube-talking-head",
  "description": "Balanced …",
  "module_enabled": { "shorts": false },
  "modules_config": {
    "retakes": { "strictness": "balanced" },
    "zooms": { "punch_in_scale": 1.15 }
  }
}
```

Presets are partial by design. Missing keys take model defaults, so a preset
stays valid when a new parameter is added. The three shipped files live in
`src/videoflow/presets/` and are validated by tests.

## 4. LLM retake payload

```json
{
  "discard_sentence_ids": [3, 4, 12],
  "reasoning": "Two aborted attempts before the final take at 13."
}
```

The response is rejected if:

- `reasoning` is empty;
- an id was not in the prompt window;
- the JSON does not match the schema.

It is then passed through the keeper guard. A response that discards the last
sentence of a cluster is corrected, not trusted.

## 5. Jobs

```json
{
  "job_id": "…",
  "project_id": "…",
  "status": "running",
  "active_module": "transcribe",
  "message": "Decoding audio"
}
```

Statuses: `queued`, `running`, `cancelled`, `succeeded`, `failed`. A project may
have at most one non-terminal job.

## 6. Errors

```json
{
  "ok": false,
  "code": "upstream_dirty",
  "message": "Cannot run zooms: upstream modules are not cached: transcribe",
  "details": { "target": "zooms", "ancestors": "transcribe" }
}
```

The Python `to_dict()` variants return lists where the schema allows richer
detail; the wire schema keeps `details` as string values so it stays simple for
agents.

## 7. Schema versioning

Any breaking state change increments `schema_version` and adds a migration. The
runner refuses to open a document with a newer version than it knows. Additive
changes with defaults do not require a version bump.

## 8. Operational store

`videoflow.db` (SQLite, WAL) is the operational store under the VideoFlow home:

| Table | Key | Payload |
| --- | --- | --- |
| `jobs` | `job_id` | Full job record, including status, stage, progress, options, result, and error |
| `assets` | `asset_id` | Asset record used by the library and timeline |
| `batches` | `batch_id` | Batch record with items and status |
| `meta` | `key` | `schema_version` and bookkeeping values |

`services` and `schedules` are created on demand by their own modules.

Rules:

1. Writes go to SQLite before the JSON mirror. A write failure never corrupts
   the mirror.
2. Reads prefer SQLite; JSON fills ids that are missing from the database, so an
   older home keeps working during migration.
3. On startup, jobs found in `queued` or `running` are re-queued as `queued`
   with `Requeued after service restart`. No partial result is reported as
   success.
4. Read helpers return an empty list when the database file does not exist and
   never create the home folder as a side effect.
5. `migrate_home()` imports `jobs/*.json`, `assets.json`, and `batches/*.json`
   and stamps `schema_version=2`.
6. `backup()` writes a consistent archive; `restore()` validates it before
   replacing the database.

The timeline document (`ProjectState`) is still the canonical edit state. SQLite
does not store the timeline.
