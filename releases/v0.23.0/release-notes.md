# VideoFlow 0.23.0

This release turns VideoFlow into a **recipe engine**. The visual editor is now
the first workspace tab, and the same DAG runs from the UI, CLI, REST API, and
MCP tools.

## Recipe engine

- Recipes are versioned JSON DAGs with stable step ids, explicit `needs`,
  typed parameter schemas, progress, cancellation, and per-step hashes.
- The engine rejects duplicate ids, unknown step types, missing dependencies,
  enabled steps that depend on disabled steps, and cycles before execution.
- The current pipeline is split into independent steps:
  `ingest`, `audio.vad`, `transcribe`, `retakes.cull`, `edit.timeline`,
  `shorts.select`, `shorts.render`, and `export.nle`.
- A parity test runs the recipe path and the legacy pipeline on the same input
  and compares cut boundaries, transcript decisions, and exports.
- Artifacts: `project_state.json`, `run.json`, NLE files under `exports/`, and
  `shorts/` plus `shorts.json` when Shorts steps are present.

## Recipes tab, first in the workspace

- A Svelte Flow canvas edits the DAG. Nodes expose JSON parameters, edges are
  dependencies, and the step palette is generated from the backend manifest.
- Load a built-in recipe, validate it, save it, download the JSON, or run it
  with live job progress.
- The classic Speech, Edit, Shorts, Studio, Export, Models, Services, and
  Providers tabs remain available.

## Interfaces

```bash
videoflow recipe list
videoflow recipe steps
videoflow recipe show viral_shorts_batch
videoflow recipe validate recipes/viral_shorts_batch.json
videoflow recipe run recipes/viral_shorts_batch.json /media/source.mp4 -o /media/out
```

REST:

- `GET /api/v1/steps`
- `GET /api/v1/recipes`
- `GET /api/v1/recipes/{id}`
- `PUT /api/v1/recipes/{id}`
- `POST /api/v1/recipes/validate`
- `POST /api/v1/recipes/run`

MCP:

- `videoflow_list_steps`
- `videoflow_list_recipes`
- `videoflow_get_recipe`
- `videoflow_validate_recipe`
- `videoflow_save_recipe`
- `videoflow_run_recipe`
- `videoflow_run_recipe_inline`

## LLM router

- `openai_compatible` is the default for Ollama, LM Studio, OpenAI, OpenRouter,
  Groq, and compatible endpoints.
- `opencode` is an opt-in one-shot CLI bridge with a timeout, no shell, output
  limits, and strict JSON parsing. It is intended for curation/planning, not
  for every caption.
- Recipes store the **name** of the API-key environment variable, never the key.

## Built-in recipes

- `youtube_talking_head` — speech cleanup, main cut, NLE exports.
- `viral_shorts_batch` — main cut plus three vertical Shorts.
- `full_podcast_curation` — main cut plus five Shorts with audio/scene boosts.

They are mirrored under `recipes/` and described in `docs/recipes.md`.

## Validation

- 391 Python tests passed; 14 UI tests passed; coverage 98.72% on the enforced
  scope.
- The AppImage was started from a detached, no-terminal session, served the
  recipes and steps APIs, rendered the Recipes tab, and executed a real recipe
  with FFmpeg-generated media.
- Opening the AppImage a second time reused the running service.

## Artifacts

- `videoflow-0.23.0-linux-x86_64` — SHA-256 `e0670a81a978b599925a87a70b2e6db1836b7bc05ebd8ff500da2be5e51988ba`
- `VideoFlow-0.23.0-x86_64.AppImage` — SHA-256 `964905d79f1189629c330e6cce2d9c0a3e1f489fe983053d411c879181fae1b5`

The build is lean; speech weights are downloaded from the Models tab. Windows
PE is not included because no Windows/Wine build host was available.
