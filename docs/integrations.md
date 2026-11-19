# Integrations: OpenCode, Paperclip, and DeepSeek

VideoFlow exposes two local surfaces:

- **REST API**: `http://127.0.0.1:8765/api/v1/...`
- **MCP**: stdio via `videoflow-mcp`, or Streamable HTTP at
  `http://127.0.0.1:8765/mcp/`

Both stay on loopback. Nothing is uploaded unless a configured provider is
explicitly allowed.

## OpenCode

### Connect the MCP server

Local stdio (recommended; starts one process per session):

```bash
opencode mcp add videoflow -- uv run videoflow-mcp
opencode mcp list
```

Remote HTTP against a running `videoflow-api`:

```bash
opencode mcp add videoflow --url http://127.0.0.1:8765/mcp/
```

Remote MCP servers default to OAuth in OpenCode. VideoFlow has no OAuth, so
disable it in `opencode.jsonc`:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "videoflow": {
        "type": "remote",
        "url": "http://127.0.0.1:8765/mcp/",
        "oauth": false
      }
    }
  }
}
```

For stdio:

```jsonc
{
  "$schema": "https://opencode.ai/config.json",
  "mcp": {
    "servers": {
      "videoflow": {
        "type": "local",
        "command": ["uv", "run", "videoflow-mcp"],
        "cwd": "/home/rafael/Documents/ProjetosAI/VideoMagic"
      }
    }
  }
}
```

### Use DeepSeek as the agent model

OpenCode already lists DeepSeek models. Pick one with `/models`, or set the
default in configuration:

```jsonc
{
  "model": "deepseek/deepseek-flash"
}
```

For the OpenCode Go gateway, `opencode-go/deepseek-v4.1-flash` is also
available. The model only drives the conversation; VideoFlow's own Copilot
provider is configured separately (below).

### Prompt that works

```text
Use the videoflow MCP tools.
1. Create the project with vf_project(action="init") for /media/interview-out.
2. Read vf://docs/steps and choose the nodes you need.
3. Run each node with vf_exec(action="step", step_id=..., params=...).
4. Poll vf_job(action="wait") after each step, then read the timeline.
5. Apply only validated vf_timeline edits.
6. Run vf_export() and report the revision, bundle manifest and paths.
```

Useful MCP tools: `vf_project`, `vf_capabilities`, `vf_catalog_search`,
`vf_exec`, `vf_job`, `vf_timeline`, `vf_artifact`, `vf_export`,
`vf_qa_final`. Recipes are intentionally UI/CLI/REST only.

## Paperclip

Paperclip ships a DeepSeek adapter (`~/.paperclip/adapters/deepseek-adapter`)
and can host agents that call MCP tools or the REST API.

### Model

1. Configure the DeepSeek adapter with `DEEPSEEK_API_KEY` (or the adapter's
   configured base URL for a local DeepSeek server).
2. Create an agent using that adapter and a model such as `deepseek-chat`.

### Tools

If your Paperclip version exposes MCP servers, add a remote server:

- URL: `http://127.0.0.1:8765/mcp/`
- OAuth: disabled (no auth on loopback)
- Tools: the `vf_*` core tools (steps, jobs, timeline, render, exports)

If your version does not expose MCP yet, the same agent can call the REST API
from a task or shell tool:

```bash
BASE=http://127.0.0.1:8765/api/v1

curl -s "$BASE/recipes" | jq '.recipes[].id'

curl -s -X POST "$BASE/recipes/run" \
  -H 'content-type: application/json' \
  -d '{
    "source": "/media/interview.mp4",
    "output": "/media/interview-out",
    "recipe_id": "youtube_talking_head"
  }' | jq '.job.job_id'
```

Then poll and edit:

```bash
JOB=<job-id>
curl -s "$BASE/jobs/$JOB" | jq '.job.status'
curl -s "$BASE/jobs/$JOB/timeline" | jq '.video'
curl -s -X POST "$BASE/jobs/$JOB/copilot/timeline" \
  -H 'content-type: application/json' \
  -d '{"prompt":"Tighten the intro and remove the last clip","apply":true}'
curl -s -X POST "$BASE/exports/validate" \
  -H 'content-type: application/json' \
  -d '{"output":"/media/interview-out"}'
```

## DeepSeek as VideoFlow's Copilot provider

VideoFlow Copilot uses the normal LLM provider chain. Either configure a
provider or set environment variables:

```bash
export VIDEOWFLOW_LLM_BASE_URL=https://api.deepseek.com/v1
export VIDEOWFLOW_LLM_MODEL=deepseek-chat
export VIDEOWFLOW_LLM_API_KEY=sk-...
export VIDEOWFLOW_ALLOWED_EXTERNAL_HOSTS=api.deepseek.com
```

Or persist it as a provider:

```bash
curl -s -X POST http://127.0.0.1:8765/api/v1/providers \
  -H 'content-type: application/json' \
  -d '{
    "id": "deepseek",
    "name": "DeepSeek",
    "capability": "llm",
    "base_url": "https://api.deepseek.com/v1",
    "model": "deepseek-chat",
    "api_key_env": "DEEPSEEK_API_KEY",
    "timeout_seconds": 120
  }'

curl -s -X POST http://127.0.0.1:8765/api/v1/providers/deepseek/default
```

For a fully local DeepSeek through Ollama/LM Studio, point `base_url` at the
local OpenAI-compatible endpoint instead and keep external services disabled.

## Security notes

- Keep the server on `127.0.0.1`; do not bind a public interface.
- External LLM calls require the provider plus the external-service policy.
  Add only the host you use (`api.deepseek.com`).
- MCP and REST have no authentication by design; anyone with local access can
  use them. Run them as your user, not as root.
- Agent prompts are data. VideoFlow validates every recipe and timeline edit
  before writing, but it cannot stop an agent from running non-VideoFlow tools.

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| OpenCode shows `needs authentication` | Remote MCP defaults to OAuth; set `"oauth": false`. |
| No VideoFlow tools listed | Run `opencode mcp list`; check the server is `connected`. |
| Copilot returns `not_implemented` / capability error | Configure an LLM provider or the `VIDEOFLOW_LLM_*` variables. |
| External call rejected | Set `allow_external_services` and the allowed host. |
| Paperclip cannot reach the server | Use `127.0.0.1`, not a container hostname; start `videoflow-api` first. |
