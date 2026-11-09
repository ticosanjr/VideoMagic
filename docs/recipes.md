# Recipes

A recipe is a versioned JSON DAG shared by the visual editor, CLI, REST API,
and MCP tools. The engine validates the graph before executing any step.

## Shape

```json
{
  "schema_version": 1,
  "id": "youtube_talking_head",
  "name": "YouTube talking head",
  "description": "Main cut and NLE exports.",
  "llm": {
    "provider": "none",
    "base_url": null,
    "model": "",
    "api_key_env": "VIDEOWFLOW_LLM_API_KEY",
    "timeout_seconds": 90
  },
  "steps": [
    { "id": "ingest", "type": "ingest", "needs": [], "params": {} },
    { "id": "vad", "type": "audio.vad", "needs": ["ingest"], "params": {} },
    { "id": "transcribe", "type": "transcribe", "needs": ["ingest"], "params": {} },
    {
      "id": "timeline",
      "type": "edit.timeline",
      "needs": ["vad", "retakes"],
      "params": {}
    }
  ]
}
```

`needs` defines execution order. A step runs once after all dependencies. The
v1 engine rejects cycles, duplicate ids, unknown types, missing dependencies,
and enabled steps that depend on disabled steps.

## Ports and wiring

`needs` ordering is not the same thing as data flow. Steps also declare typed
inputs and outputs, and a recipe can bind a specific output to a specific input:

```json
{
  "id": "timeline_tight",
  "type": "edit.timeline",
  "needs": ["vad_tight", "transcribe"],
  "inputs": {
    "speech": "vad_tight.speech",
    "transcript": "transcribe.transcript"
  },
  "params": { "cut_mode": "j_cut", "offset_ms": 180 }
}
```

Core port types are `media`, `pcm`, `sample_spans`, `inactive_spans`,
`transcript`, `timeline`, `short_list`, `artifact_map`, and `any`. The runner
rejects unknown ports, type mismatches, missing required inputs, and sources
that are not in the dependency ancestry. Existing recipes without `inputs` keep
the legacy implicit context behaviour.

`audio.vad` exposes `silence`, `retakes.cull` exposes `retakes`, and
`edit.timeline` accepts both. The timeline step treats their union as the
reason map for the automatic inactive segments.

In the UI, each node shows its ports. The inspector lists every input with a
compatible-output dropdown, so wiring never requires dragging; clicking an edge
or dragging a connection opens the **Wire ports** dialog as well. The edge label
shows the mapping, for example `speech → speech`.

Wiring enables branches: two VADs with different thresholds, two timelines with
different cut modes, and a comparison between them. The cache fingerprint
includes the wired input hashes, so changing one branch does not invalidate the
other.

## Node controls

The inspector is generated from each step's JSON schema:

- bounded numbers render as sliders with a numeric companion;
- short enums render as segmented buttons and longer enums as dropdowns;
- booleans render as switches;
- string arrays and export targets render as chips;
- paths use the path picker, colours use a picker plus hex;
- complex objects/arrays keep a JSON editor;
- each field shows its default and offers **Reset to default**;
- nodes expose presets (Gentle/Balanced/Aggressive/Tight for VAD,
  Hard/J/L/Custom for cuts, Conservative/Balanced/Aggressive for retakes).

All Recut defaults live inside the nodes. Recipe variables remain reserved for
values genuinely shared by multiple nodes or profiles.

## Steps

| Type | Requires | Produces |
| --- | --- | --- |
| `ingest` | — | media, PCM, digest |
| `audio.vad` | `ingest` | speech intervals, silence spans, VAD engine |
| `transcribe` | `ingest` | transcript (SRT, project, Faster-Whisper, whisper.cpp, HTTP, or none) |
| `retakes.cull` | `audio.vad`, `transcribe` | discard/restore decisions, retake/manual spans, updated speech |
| `audio.diarize` | `transcribe` | heuristic or pyannote speaker ids for captions |
| `broll.plan` | `shorts.select` | local or Pexels B-roll overlay plan |
| `edit.timeline` | `audio.vad` (+ optional retakes) | validated `ProjectState`, inactive spans |
| `timeline.load` | — | saved `ProjectState` and media info |
| `shorts.select` | `transcribe` | selected Short clips |
| `shorts.score` | `shorts.select` | re-scored, deduplicated Shorts |
| `assets.shots` | `ingest` | scene cuts + thumbnails |
| `assets.match` | `shorts.select` | semantic B-roll matches |
| `music.beat` | — | deterministic beat grid |
| `sfx.plan` | — | SFX cue plan |
| `metadata.pack` | `shorts.select` | per-Short metadata |
| `thumbnail.pack` | `shorts.render` | thumbnail variants |
| `publish.queue` | `shorts.render` | queued publishing items |
| `analytics.review` | — | selection weights/recommendations |
| `experiment.evaluate` | — | A/B winner |
| `chapters.plan` | `transcribe` | chapter markers |
| `nle.qa` | `export.nle` | NLE validation report |
| `human.gate` | — | pause/resume approval |
| `flow.map` | — | per-item results |
| `flow.reduce` | — | best/top-K selection |
| `shorts.reframe` | `shorts.select` | crop focus via static crop, motion, or face tracking |
| `shorts.captions` | `shorts.select` | ASS caption files per Short |
| `shorts.render` | `shorts.select` (+ optional reframe/captions) | MP4 + `shorts.json`; uses caption files when present |
| `export.nle` | `edit.timeline` | FCPXML/Resolve, XMEML/Premiere, and Kdenlive timelines |
| `export.video` | `edit.timeline` or `timeline.load` | Direct video file with ultrafast/fast/balanced/quality presets |

`GET /api/v1/steps` returns each step's JSON parameter schema. The UI uses that
manifest to generate node defaults, so new steps do not require a new node
component.

## CLI

```bash
videoflow recipe list
videoflow recipe steps
videoflow recipe show viral_shorts_batch
videoflow recipe validate recipes/viral_shorts_batch.json
videoflow recipe run recipes/viral_shorts_batch.json /media/source.mp4 -o /media/out
videoflow recipe step recipes/viral_shorts_batch.json shorts /media/source.mp4 -o /media/out
videoflow recipe run recipes/viral_shorts_batch.json /media/source.mp4 -o /media/out --force
videoflow recipe batch recipes/viral_shorts_batch.json /media/inbox -o /media/out --recursive
```

## REST

```http
GET  /api/v1/steps
GET  /api/v1/recipes
GET  /api/v1/recipes/{id}
PUT  /api/v1/recipes/{id}
POST /api/v1/recipes/validate
POST /api/v1/recipes/run
POST /api/v1/steps/{step_id}/run
POST /api/v1/batches
GET  /api/v1/batches
GET  /api/v1/batches/{id}
POST /api/v1/batches/{id}/cancel
```

`POST /api/v1/recipes/run` accepts either a complete `recipe` object or a
`recipe_id`, plus optional `source`, `output`, `through`, `resume`, and
`transcript_sentences`. When `source` is omitted it comes from the ingest node
in the recipe; when `output` is omitted it defaults to
`<source>-videoflow`. The UI runs with both omitted and reads the resolved
output from the returned job record. The endpoint returns the normal job
record, so existing job status, logs, SSE, cancellation, and artifact routes
apply.

`POST /api/v1/steps/{step_id}/run` runs only that step and its dependency
closure, using the same request body. It is the step-scoped form of the same
job.

## MCP

- `videoflow_list_steps`
- `videoflow_list_recipes`
- `videoflow_get_recipe`
- `videoflow_validate_recipe`
- `videoflow_save_recipe`
- `videoflow_run_recipe`
- `videoflow_run_recipe_inline`
- `videoflow_run_step` — dependencies plus one named step, then stop
- `videoflow_run_batch` — run a recipe over a folder
- `videoflow_get_batch` / `videoflow_cancel_batch` — inspect or cancel a folder batch

Agents should call `videoflow_run_recipe` and then poll `videoflow_get_job`.
The MCP server and the UI share the same `JobManager`.

## LLM router

`llm.provider` is one of:

- `none` — local-only; deterministic steps still run.
- `openai_compatible` — Ollama, LM Studio, OpenAI, OpenRouter, Groq, or any
  endpoint with `/chat/completions`.
- `opencode` — opt-in one-shot CLI bridge for curation/planning, with a
  timeout, no shell, output limits, and strict JSON parsing.

Secrets are referenced by environment variable name. A recipe never contains
an API key.

## Cache

`audio.vad` and local/HTTP `transcribe` results are cached by source PCM digest
plus step parameters under:

```text
<videoflow-home>/cache/recipe-v1/
```

The cache is shared across output directories, so a second recipe run can reuse
VAD and a local/HTTP transcript even when the project folder changes. Use:

```bash
videoflow recipe cache path
videoflow recipe cache clear
```

Set `VIDEOWFLOW_RECIPE_CACHE=0` to disable it. SRT/project transcripts are read
directly and are not cached. The run report lists `cache_hits` and
`cache_misses`.

### Per-step checkpoints

Each successful step also writes a checkpoint under:

```text
<output>/work/steps/<step_id>/
  manifest.json
  snapshot.json
```

The fingerprint covers the step type/version, validated parameters, source
fingerprint, and upstream step hashes. On the next run in the same output
directory, matching steps are reused and reported as `cached`; changing a step
parameter invalidates that step and its dependents. File-producing steps also
verify that their declared outputs still exist.

Use `--force` to ignore checkpoints and execute every step. The report and job
result expose `step_runs`:

```json
{"id": "vad", "type": "audio.vad", "status": "cached", "elapsed_ms": 0}
```

The visual editor colors each node as `cached`, `executed`, `running`, or
`failed`, and the step inspector has **Run to here** for a partial run.

## Folder batches

`POST /api/v1/batches` runs a recipe over every matching media file in a folder.
Files are processed one at a time, each into its own output folder, and each
item is a normal job with its own progress, cancellation, logs, and checkpoints.

```bash
videoflow recipe batch recipes/viral_shorts_batch.json /media/inbox -o /media/out --recursive
```

Request fields: `source_dir`, `output_root`, `recipe` or `recipe_id`,
`recursive`, `extensions`, `resume`, and `max_files`. The UI exposes the same
flow through the **Batch** modal. `GET /api/v1/batches/{id}` returns item-level
status.

## Video export

The `export.video` node is separate from `export.nle`. `export.nle` only writes
editing timelines; `export.video` renders the final video. Its default is
`ultrafast` (libx264 `ultrafast`, CRF 30), the fastest practical H.264/AAC MP4
profile. Built-in recipes end with both nodes. Use the node header dot or the
inspector toggle to disable either exporter without deleting it. Disabled nodes
are omitted from the run and their parameters stay saved. Wired inputs are
automatically added to `needs` on load, repairing older recipes that failed with
"source timeline must run earlier".

## Direct MP4

`export.nle` accepts `mp4` in its `targets` list. The exporter builds one FFmpeg
filter graph from the validated timeline, applies J/L-cut audio ranges and
static transforms, and writes H.264/AAC with `+faststart`. The Recut recipes do
not include `mp4` by default; render it from the Edit tab so the MP4 cannot block
the timeline from opening. The legacy job form also exposes an **MP4** target.

## Artifacts

Every run writes:

- `project_state.json` — the validated timeline, when a timeline step exists.
- `run.json` — summary, recipe, step list, hashes, warnings, artifacts.
- `exports/` — NLE documents.
- `shorts/` and `shorts.json` — when Shorts steps are present.

The legacy pipeline was removed in 2.59.4; recipe jobs are the only execution path and are covered by
a parity test against the recipe path.


## Variables

```json
{
  "variables": {
    "aspect": {"type": "enum", "default": "9:16", "options": ["9:16", "1:1", "16:9"]},
    "caption_size": {"type": "number", "default": 72},
    "platform": {"type": "string", "default": "youtube"}
  },
  "steps": [
    {"id": "shorts", "type": "shorts.select", "params": {"aspect_ratio": "$aspect"}},
    {"id": "captions", "type": "shorts.captions", "params": {"caption_style": {"font_size": "{{ caption_size }}"}}}
  ]
}
```

`$name` substitutes the typed value; `{{ expression }}` evaluates a safe
expression with `min`, `max`, `clamp`, `if`, `coalesce`, `round`, `len`, and
arithmetic/comparison operators.

## Profiles

```json
{
  "profiles": {
    "fast": {"variables": {"caption_size": {"default": 64}}, "steps": {"timeline": {"transition_frames": 0}}}
  }
}
```

The CLI uses `--profile fast`; the API uses `"profile": "fast"`.

## Variants

```json
{
  "variants": [
    {"name": "9x16", "variables": {"aspect": "9:16"}},
    {"name": "1x1", "variables": {"aspect": "1:1"}}
  ]
}
```

Each variant runs into `output/<name>` and the job result lists each summary.

## Flow control

- `flow.conditional`: true/false branches.
- `flow.loop`: repeat inline steps over Shorts or files.
- `flow.map`: per-item execution with `collect` and `on_error`.
- `flow.reduce`: `best_of`, `top_k`, or `all`.
- `flow.subflow`: reusable inline/referenced steps.

## Human gates

```json
{
  "id": "review",
  "type": "human.gate",
  "needs": ["shorts"],
  "params": {"gate_id": "shorts", "title": "Approve Shorts"}
}
```

The job stops as `waiting_approval`. `POST /api/v1/jobs/{id}/resume` writes
`approvals/<gate>.json` and restarts from checkpoints.

## Built-in recipes

`localized_shorts` extends `viral_shorts_batch` with a `localization.dub` step
after the Shorts render. It is skipped with a warning when no TTS provider is
configured.

The catalog includes 44 recipes: rough cut, captions, NLE export, clean audio,
chapters, Shorts select/render, best moments, hook first, trailer, review gate,
reframe/caption/A-B variants, podcast, interview, webinar, lecture, product
demo, testimonial, livestream, B-roll, music, SFX, metadata, thumbnails,
publishing, analytics, localization, and finishing.

`full_ai_editor` is the long-form, human-reviewed documentary recipe. It pauses
for the editorial brief, research datasets, script lock, decoupage audit, entity
corrections, style lock, sample homologation, fact-check, and final approval.
See [hilt.md](hilt.md) for the checkpoint contract.

## CLI

```bash
videoflow recipe run youtube_talking_head source.mp4 -o out
videoflow recipe run viral_shorts_batch source.mp4 -o out --var aspect=1:1
videoflow recipe run content_cycle source.mp4 -o out --profile fast --dry-run
```

## Recut Replacement

Two built-in recipes focus on removing silence before any creative edit:

| Recipe | Steps | Use |
| --- | --- | --- |
| `recut_replacement` | ingest → vad → timeline → export | Fast, deterministic silence recut |
| `recut_replacement_retakes` | ingest → vad → transcribe → retakes → timeline → export | Silence recut plus retake culling |

Both export **FCPXML (Resolve), XMEML (Premiere), and Kdenlive** from the same
timeline. The MP4 is rendered from the Edit tab after the cut is final, so NLE
export cannot block timeline editing.

### Silence controls

| Variable | Default | Meaning |
| --- | ---: | --- |
| `engine` | `auto` | `auto`, `silero`, or `ffmpeg` |
| `noise_db` | -30 | FFmpeg fallback threshold (-80 to -5 dB) |
| `speech_threshold` | 0.5 | Silero speech probability (0.1–0.9) |
| `min_silence_ms` | 350 | Pause length that counts as removable silence |
| `min_speech_ms` | 120 | Shortest speech span kept |
| `spike_suppression_ms` | 180 | Drop isolated sounds shorter than this |
| `merge_gap_ms` | 120 | Bridge speech separated by tiny gaps |
| `pad_before_ms` | 80 | Left handle kept around speech |
| `pad_after_ms` | 120 | Right handle kept around speech |

### Cut controls

| Variable | Default | Meaning |
| --- | ---: | --- |
| `cut_mode` | `hard` | `hard`, `j_cut`, `l_cut`, or `custom` |
| `enable_j_cuts` | false | Used only when `cut_mode=custom` |
| `enable_l_cuts` | false | Used only when `cut_mode=custom` |
| `offset_ms` | 200 | J/L audio offset (100–500 ms) |
| `audio_crossfade_ms` | 20 | Micro-fade at cut boundaries |
| `fade_in_ms` / `fade_out_ms` | 20 | Clip fades |
| `handle_check` | true | Verify source handles before shifting audio |
| `transition_frames` | 0 | Optional crossfade/fade-to-black between cuts |
| `transition_type` | `crossfade` | `crossfade` or `fade_to_black` |

In `hard` mode both legacy J/L booleans are forced off; `j_cut` and `l_cut`
force exactly one direction. `custom` keeps the booleans for advanced graphs.

## Favorites and recents

Favorites and recent runs are stored locally on the server in
`<home>/recipe_meta.json`, so the REST API, MCP tools, and every UI session see
the same organization.

- `GET /api/v1/recipes` includes `favorite`, `last_used_at`, `use_count`, `tags`.
- `POST /api/v1/recipes/{id}/favorite` with `{"favorite": true|false}`.
- `POST /api/v1/recipes/{id}/touch` records a run.
- `PATCH /api/v1/recipes/{id}/meta` with `{"tags": [...]}`.

`recut_replacement` and `recut_replacement_retakes` are favorites by default.
