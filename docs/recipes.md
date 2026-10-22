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

## Steps

| Type | Requires | Produces |
| --- | --- | --- |
| `ingest` | — | media, PCM, digest |
| `audio.vad` | `ingest` | speech intervals, VAD engine |
| `transcribe` | `ingest` | transcript (SRT, project, Faster-Whisper, whisper.cpp, HTTP, or none) |
| `retakes.cull` | `transcribe` | discard/restore decisions, updated speech |
| `edit.timeline` | `audio.vad` | validated `ProjectState` |
| `shorts.select` | `transcribe` | selected Short clips |
| `shorts.render` | `shorts.select` | MP4 + ASS files and `shorts.json` |
| `export.nle` | `edit.timeline` | FCPXML, XMEML, Kdenlive |

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
```

## REST

```http
GET  /api/v1/steps
GET  /api/v1/recipes
GET  /api/v1/recipes/{id}
PUT  /api/v1/recipes/{id}
POST /api/v1/recipes/validate
POST /api/v1/recipes/run
```

`POST /api/v1/recipes/run` accepts either a complete `recipe` object or a
`recipe_id`, plus `source`, `output`, and optional `transcript_sentences`. It
returns the normal job record, so existing job status, logs, SSE, cancellation,
and artifact routes apply.

## MCP

- `videoflow_list_steps`
- `videoflow_list_recipes`
- `videoflow_get_recipe`
- `videoflow_validate_recipe`
- `videoflow_save_recipe`
- `videoflow_run_recipe`
- `videoflow_run_recipe_inline`

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

## Artifacts

Every run writes:

- `project_state.json` — the validated timeline, when a timeline step exists.
- `run.json` — summary, recipe, step list, hashes, warnings, artifacts.
- `exports/` — NLE documents.
- `shorts/` and `shorts.json` — when Shorts steps are present.

The legacy pipeline remains available at `POST /api/v1/jobs` and is covered by
a parity test against the recipe path.
