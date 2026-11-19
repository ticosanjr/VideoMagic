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
Workflow: vf_project -> vf_catalog_search -> vf_exec(action="step") ->
vf_job -> vf_timeline -> vf_export`
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
  <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="vf-label text-sky-300/80">MCP</p>
        <h2 class="mt-1 text-[length:var(--vf-text-lg)] font-semibold text-white">Connect an MCP client</h2>
        <p class="mt-1 max-w-2xl text-[length:var(--vf-text-xs)] text-neutral-500">
          VideoFlow is controlled through MCP. Copy one block into OpenCode, Paperclip, or another MCP client.
        </p>
      </div>
      <HelpTip
        label="Transport"
        body="The server stays on loopback. Use stdio for a single local client or HTTP for several agents."
      />
    </div>
  </div>

  <div class="grid gap-3">
    {#each blocks as block (block.id)}
      <article class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
        <div class="flex items-center justify-between gap-3">
          <h3 class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">{block.title}</h3>
          <button
            type="button"
            onclick={() => void copy(block.id, block.text)}
            class="rounded-lg border border-white/10 px-2.5 py-1 text-[length:var(--vf-text-xs)] text-neutral-300 hover:border-sky-500/40"
          >{copied === block.id ? "Copied" : "Copy"}</button>
        </div>
        <pre class="mt-3 overflow-x-auto rounded-xl bg-black/40 p-3 font-mono text-[length:var(--vf-text-xs)] leading-5 text-neutral-300">{block.text}</pre>
      </article>
    {/each}
  </div>
</section>
