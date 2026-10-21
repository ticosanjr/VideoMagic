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
  "schema_version": 1,
  "project_id": "8d1d4f0e-...",
  "revision": 1,
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

- `schema_version` is `1`.
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
| `TranscribeConfig` | engine `auto`/`faster-whisper`/`whisper.cpp`, enum model, language, device, compute type; Faster-Whisper VAD off by default |
| `RetakesConfig` | no secret value; `secret_name` only; temperature fixed at 0 |
| `JlCutsConfig` | offset 100–500 ms, crossfade 10–50 ms |
| `ZoomsConfig` | scale 1.05–1.30 |
| `ShortsConfig` | min ≤ max; 1–20 clips; prompt/reprompt; replace/refine; hook off/metadata/repeat/reorder; filler list; aspect 9:16/1:1/16:9; source end > start |
| `ProvidersConfig` | external services opt-in; optional remote-host allowlist |
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
