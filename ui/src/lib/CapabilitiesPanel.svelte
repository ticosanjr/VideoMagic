<script lang="ts">
  import { onMount } from "svelte";
  import {
    errorMessage,
    getCapabilities,
    type Capability,
    type CapabilitiesResponse
  } from "$lib/api";

  let {
    allowExternal = false,
    allowedHosts = "",
    onToggle,
    onHosts
  }: {
    allowExternal: boolean;
    allowedHosts: string;
    onToggle: (value: boolean) => void;
    onHosts: (value: string) => void;
  } = $props();

  let response = $state<CapabilitiesResponse | null>(null);
  let loading = $state(true);
  let error = $state("");

  const categories = ["ingest", "speech", "shorts", "export", "providers", "curation", "editing", "audio"];

  const grouped = $derived(
    categories
      .map((category) => ({
        category,
        items: (response?.capabilities ?? []).filter((item) => item.category === category)
      }))
      .filter((group) => group.items.length > 0)
  );

  const statusStyles: Record<string, string> = {
    available: "bg-emerald-400/10 text-emerald-300 ring-emerald-400/20",
    blocked: "bg-rose-400/10 text-rose-300 ring-rose-400/20",
    partial: "bg-amber-400/10 text-amber-300 ring-amber-400/20",
    planned: "bg-neutral-800 text-neutral-400 ring-neutral-700"
  };

  async function refresh(value = allowExternal) {
    loading = true;
    error = "";
    try {
      response = await getCapabilities(value);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      loading = false;
    }
  }

  function toggle(value: boolean) {
    onToggle(value);
    void refresh(value);
  }

  onMount(() => {
    void refresh();
  });
</script>

<div class="space-y-4">
  <div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-start justify-between gap-4">
      <div>
        <h2 class="text-sm font-semibold">Providers and capabilities</h2>
        <p class="mt-1 max-w-2xl text-xs leading-5 text-neutral-400">
          Local features work offline. External services are opt-in per run and can be
          blocked globally with <code class="rounded bg-neutral-800 px-1 py-0.5 text-[10px]">VIDEOWFLOW_ALLOW_EXTERNAL=0</code>.
          API keys stay in the environment; project state stores only the secret name.
        </p>
      </div>
      <span
        class="rounded-full px-3 py-1 text-[11px] font-medium ring-1 {response?.external_services_allowed
          ? 'bg-emerald-400/10 text-emerald-300 ring-emerald-400/20'
          : 'bg-neutral-800 text-neutral-400 ring-neutral-700'}"
      >
        {response?.external_services_allowed ? "External services allowed" : "Offline policy"}
      </span>
    </div>

    <label class="mt-4 flex items-center gap-3 rounded-xl border border-neutral-800 bg-neutral-950/60 p-3 text-xs text-neutral-300">
      <input
        type="checkbox"
        checked={allowExternal}
        onchange={(event) => toggle(event.currentTarget.checked)}
        class="h-4 w-4 rounded border-neutral-700 bg-neutral-800"
      />
      <span>
        Allow external providers for the next run
        <span class="block text-[10px] text-neutral-500">
          Local providers (localhost) are always allowed. This flag covers remote LLM/ASR and future providers.
        </span>
      </span>
    </label>

    <label class="mt-2 block rounded-xl border border-neutral-800 bg-neutral-950/60 p-3 text-xs text-neutral-300">
      <span class="text-[10px] uppercase tracking-wide text-neutral-500">Allowed external hosts</span>
      <input
        type="text"
        value={allowedHosts}
        oninput={(event) => onHosts(event.currentTarget.value)}
        placeholder="api.openai.com, api.elevenlabs.io"
        class="mt-1.5 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 font-mono text-[11px] text-neutral-100 placeholder:text-neutral-600"
      />
      <span class="mt-1 block text-[10px] text-neutral-500">
        Comma-separated allowlist. Empty means any remote host while external access is on.
      </span>
    </label>
  </div>

  {#if loading}
    <div class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4 text-xs text-neutral-500">
      Reading capabilities…
    </div>
  {:else if error}
    <div class="rounded-2xl border border-rose-500/20 bg-rose-950/20 p-4 text-xs text-rose-300">
      {error}
    </div>
  {:else}
    <div class="grid gap-3 lg:grid-cols-2">
      {#each grouped as group}
        <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
          <h3 class="text-[11px] font-semibold uppercase tracking-wide text-neutral-500">
            {group.category}
          </h3>
          <div class="mt-3 space-y-2">
            {#each group.items as item}
              <article class="rounded-xl border border-neutral-800 bg-neutral-950/50 p-3">
                <div class="flex flex-wrap items-start justify-between gap-2">
                  <div class="min-w-0">
                    <p class="text-xs font-medium text-neutral-200">{item.name}</p>
                    <p class="mt-0.5 text-[10px] leading-4 text-neutral-500">{item.description}</p>
                  </div>
                  <span class="rounded-full px-2 py-0.5 text-[9px] font-medium uppercase tracking-wide ring-1 {statusStyles[item.status] ?? statusStyles.planned}">
                    {item.status}
                  </span>
                </div>
                {#if item.reason}
                  <p class="mt-2 text-[10px] leading-4 text-rose-300/80">{item.reason}</p>
                {/if}
                <dl class="mt-2 grid gap-1 text-[9px] text-neutral-600 sm:grid-cols-2">
                  <div><dt class="inline text-neutral-500">API </dt><dd class="inline font-mono">{item.api}</dd></div>
                  <div><dt class="inline text-neutral-500">MCP </dt><dd class="inline font-mono">{item.mcp}</dd></div>
                </dl>
              </article>
            {/each}
          </div>
        </section>
      {/each}
    </div>
  {/if}
</div>
