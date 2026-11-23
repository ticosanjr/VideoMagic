# Intelligence

VideoFlow routes every model-backed task through one intelligence layer.
Providers are optional; deterministic steps keep working without a model.

## Provider order

Default:

```text
opencode_v2 -> deepseek -> openai_compatible -> none
```

- `opencode_v2` uses the local OpenCode V2 HTTP API.
- `deepseek` uses the DeepSeek OpenAI-compatible endpoint.
- `openai_compatible` covers Ollama, LM Studio, vLLM, Groq, OpenRouter, and
  similar endpoints.
- `opencode_cli` is the legacy one-process bridge.

Remote providers require network access. OpenCode local is always allowed.
When every provider fails, the task either uses its deterministic fallback or
returns a typed capability error.

## OpenCode V2

Configure `Intelligence -> OpenCode base URL`, default
`http://127.0.0.1:4096`, and optionally a token env.

Used endpoints:

| Operation | Endpoint |
| --- | --- |
| Health | `GET /api/info` |
| Models | `GET /api/model?types=chat` |
| Text | `POST /api/experimental/generate/text` |
| Image | `POST /api/experimental/generate/image` |

Text calls send a prompt with an explicit JSON schema instruction and parse
`data.text`. Image calls send `{model, prompt, n, aspect, resolution}` and decode
`data.images[].data`. The server is never started implicitly.

## Settings

`settings.json`:

```json
{
  "intelligence": {
    "enabled": true,
    "provider_order": ["opencode_v2", "deepseek", "openai_compatible"],
    "allow_network": false,
    "budget_usd": 0,
    "opencode_base_url": "http://127.0.0.1:4096",
    "opencode_model": "",
    "opencode_token_env": "OPENCODE_TOKEN",
    "deepseek_base_url": "https://api.deepseek.com",
    "deepseek_model": "deepseek-chat",
    "deepseek_api_key_env": "DEEPSEEK_API_KEY",
    "tasks": {}
  }
}
```

A task policy can override the provider order, model, temperature, max tokens,
timeout, fallback mode, and enabled flag.

## Tasks

High-value tasks:

- `curation.select`, `curation.score`, `curation.hook`
- `cleanup.context`, `retakes.semantic`
- `narrative.beats`, `timeline.edit`, `timeline.zoom`, `timeline.style`
- `style.guide`
- `script.dual`
- `metadata.social`
- `factcheck.audit`
- `translation.transcript`, `dubbing.translate`
- `caption.emoji`
- `copilot.recipe`, `copilot.timeline`, `assistant.plan`
- `image.broll`, `thumbnail.curate`, `chapters.title`, `publish.copy`
- `vision.analyze`, `eval.judge`

Deterministic math is never sent to a model: timebase, VAD, silence, cuts,
crop geometry, licensing, budget arithmetic, and cache keys.

## Scoring

`shorts.score` supports:

- `heuristic` — current deterministic score.
- `llm` — model score, arc, and justification.
- `hybrid` — average of heuristic and model score.

The model returns:

```json
{
  "score": 87,
  "arc": "hook|development|climax|cta",
  "hook": "...",
  "climax": "...",
  "cta": "...",
  "justification": "..."
}
```

The result is clamped and validated. A failed call falls back to the heuristic
and records a warning.

## Telemetry

`GET /api/v1/intelligence/status` returns provider readiness and per-task
telemetry. `GET /api/v1/intelligence/tasks` returns task policies.
`GET /api/v1/intelligence/models?provider=opencode_v2` lists models.

Job output records provider, model, task, tokens, cost, latency, and fallback
reason. Secrets, raw prompts, and response bodies are never logged.

## Failure behavior

- Provider offline: next provider.
- Invalid JSON: one repair attempt, then next provider.
- Budget exceeded: stop paid providers; deterministic fallback.
- No provider: deterministic fallback or a typed capability error.
- No silent fabricated output.
