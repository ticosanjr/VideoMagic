<script lang="ts">
  import HelpTip from "$lib/HelpTip.svelte";
  import { onMount } from "svelte";

  let origin = $state("http://127.0.0.1:8765");
  let copied = $state("");

  onMount(() => {
    if (typeof window !== "undefined") origin = window.location.origin;
  });

  const blocks = $derived([
    {
      id: "mcp-stdio",
      title: "MCP (stdio)",
      text: "opencode mcp add videoflow -- uv run videoflow-mcp"
    },
    {
      id: "mcp-http",
      title: "MCP (HTTP)",
      text: `opencode mcp add videoflow --url ${origin}/mcp/`
    },
    {
      id: "opencode-config",
      title: "opencode.jsonc",
      text: `{
  "$schema": "https://opencode.ai/config.json",
  "model": "deepseek/deepseek-flash",
  "mcp": {
    "servers": {
      "videoflow": {
        "type": "remote",
        "url": "${origin}/mcp/",
        "oauth": false
      }
    }
  }
}`
    },
    {
      id: "deepseek",
      title: "DeepSeek provider",
      text: `export VIDEOWFLOW_LLM_BASE_URL=https://api.deepseek.com/v1
export VIDEOWFLOW_LLM_MODEL=deepseek-chat
export VIDEOWFLOW_LLM_API_KEY=sk-...
export VIDEOWFLOW_ALLOWED_EXTERNAL_HOSTS=api.deepseek.com`
    },
    {
      id: "paperclip",
      title: "Paperclip",
      text: `Agent model: DeepSeek adapter (deepseek-chat)
MCP server: ${origin}/mcp/   (OAuth disabled)
Workflow: videoflow_list_recipes -> videoflow_run_recipe ->
videoflow_get_job -> videoflow_get_timeline -> videoflow_copilot_timeline ->
videoflow_validate_exports`
    },
    {
      id: "api",
      title: "REST API",
      text: `curl -s ${origin}/api/v1/recipes | jq '.recipes[].id'

curl -s -X POST ${origin}/api/v1/jobs/JOB/copilot/timeline \\
  -H 'content-type: application/json' \\
  -d '{"prompt":"Tighten the intro and remove the last clip","apply":true}'`
    }
  ]);

  async function copy(id: string, text: string) {
    try {
      await navigator.clipboard.writeText(text);
      copied = id;
      setTimeout(() => (copied = ""), 1500);
    } catch {
      copied = "";
    }
  }
</script>

<section class="space-y-4" data-testid="integrations-panel">
  <header>
    <div class="flex items-center gap-1.5"><h2 class="text-lg font-semibold text-white">Integrations</h2> <HelpTip label="Connect" body="MCP and REST entry points for OpenCode and Paperclip, with DeepSeek as the model. Everything is loopback." doc="docs/integrations.md" /></div>
    <p class="mt-1 text-xs text-neutral-500">
      Drive VideoFlow from OpenCode or Paperclip through MCP or REST, with DeepSeek as the agent or Copilot model. Everything stays on loopback.
    </p>
  </header>

  <div class="grid gap-3 lg:grid-cols-2">
    {#each blocks as block (block.id)}
      <article class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
        <div class="flex items-center justify-between gap-2">
          <h3 class="text-xs font-semibold text-neutral-100">{block.title}</h3>
          <button
            type="button"
            class="rounded-lg border border-white/10 px-2 py-0.5 text-[10px] text-neutral-400 hover:text-sky-200"
            onclick={() => void copy(block.id, block.text)}
          >{copied === block.id ? "Copied" : "Copy"}</button>
        </div>
        <pre class="mt-2 max-h-56 overflow-auto rounded-xl border border-neutral-800 bg-black/50 p-3 text-[10px] leading-relaxed text-neutral-300">{block.text}</pre>
      </article>
    {/each}
  </div>

  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4 text-[11px] text-neutral-400">
    <p class="font-medium text-neutral-200">Suggested agent prompt</p>
    <p class="mt-1">
      “Use the videoflow MCP tools. List recipes, run the best one for this source, poll until success, read the timeline, apply validated Copilot edits, export, and validate the three NLE documents.”
    </p>
    <p class="mt-2 text-neutral-500">
      Keep the server on 127.0.0.1. External LLM calls require the provider plus the external-service allowlist. See <span class="font-mono">docs/integrations.md</span> for Paperclip and troubleshooting.
    </p>
  </section>
</section>
