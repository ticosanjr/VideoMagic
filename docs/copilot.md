# Copilot

Copilot turns natural language into validated VideoFlow changes. It never
writes outside the normal engine: a recipe draft is parsed and its graph
validated, and a timeline plan is applied one edit at a time through
`apply_timeline_edit`.

## Configure the LLM

### As a provider (recommended)

Use the Providers tab or `POST /api/v1/providers` with an OpenAI-compatible
endpoint:

```json
{
  "id": "local-llm",
  "name": "Local LLM",
  "capability": "llm",
  "base_url": "http://127.0.0.1:11434/v1",
  "model": "qwen2.5:7b-instruct",
  "api_key_env": "VIDEOWFLOW_LLM_API_KEY",
  "timeout_seconds": 120
}
```

`POST /api/v1/providers/local-llm/default` makes it the default. Copilot uses
`resolve_chain("llm")`, so configured fallbacks are tried in order.

Alternative without the provider UI:

```bash
export VIDEOWFLOW_LLM_BASE_URL=http://127.0.0.1:11434/v1
export VIDEOWFLOW_LLM_MODEL=qwen2.5:7b-instruct
```

### As a managed service

In Services, define a local server command (for example `ollama serve`) with a
health URL of `http://127.0.0.1:11434/`, enable autostart, and then add the
provider above. VideoFlow starts the service and Copilot talks to it over
loopback.

## Recipe drafts

```http
POST /api/v1/copilot/recipe
{"prompt": "Clean audio, captions, three vertical Shorts and NLE exports"}
```

The response is a recipe object that already passed `parse_recipe` and
`validate_graph`. The Copilot tab can save it directly to the local library.

## Timeline edits

```http
POST /api/v1/jobs/{job_id}/copilot/timeline
{"prompt": "Tighten the first clip and remove the last one", "apply": true}
```

The model must answer with `edits` using only existing clip ids and the
supported actions: `trim`, `move`, `split`, `delete`, `ripple`,
`ripple_trim`, `slip`, `slide`, `duplicate`. Unknown ids or actions are
rejected before anything is written. Applied edits record one undo entry and
increment `revision`.

## What it does not do

- It does not execute arbitrary shell or MCP tools; the proposal is limited to
  recipe JSON and timeline edit objects.
- It does not call external services unless the provider and the normal
  external-service policy allow it.
- Voice cloning and arbitrary extension code remain outside the Copilot contract.

## Tests

- `tests/unit/test_copilot.py`: recipe validation, unknown action/clip
  rejection, edit acceptance.
- `tests/contract/test_api_copilot.py`: recipe endpoint and applied timeline
  edit through the real API.
