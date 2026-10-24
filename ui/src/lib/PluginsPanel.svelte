<script lang="ts">
  import { onMount } from "svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import { errorMessage } from "$lib/api";

  type Plugin = {
    id: string;
    name: string;
    version: string;
    enabled: boolean;
    loaded?: boolean;
    provides?: string[];
    permissions?: string[];
    sandbox?: string[];
    error?: string;
  };
  type Panel = { id: string; title: string; url: string };

  let plugins = $state<Plugin[]>([]);
  let panels = $state<Panel[]>([]);
  let error = $state("");
  let busy = $state("");
  let activePanel = $state("");

  async function load(reload = false) {
    try {
      const response = await fetch(reload ? "/api/v1/plugins/reload" : "/api/v1/plugins", {
        method: reload ? "POST" : "GET"
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload?.detail?.message ?? "Plugin request failed");
      plugins = payload.plugins ?? [];
      panels = payload.panels ?? [];
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function toggle(plugin: Plugin) {
    if (!confirm(`${plugin.enabled ? "Disable" : "Enable"} plugin ${plugin.id}?`)) return;
    busy = plugin.id;
    try {
      await fetch(`/api/v1/plugins/${encodeURIComponent(plugin.id)}/enable`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !plugin.enabled })
      });
      await load(true);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = "";
    }
  }

  onMount(() => void load());
</script>

<section class="space-y-4" data-testid="plugins-panel">
  <header class="flex flex-wrap items-end justify-between gap-3">
    <div>
      <h2 class="text-lg font-semibold text-white">Plugins</h2>
      <p class="mt-1 text-xs text-neutral-500">
        Local packages that add steps, exporters, providers, or panels. Only trusted code is allowed.
      </p>
    </div>
    <button
      type="button"
      onclick={() => void load(true)}
      class="rounded-xl border border-white/10 px-3 py-1.5 text-xs text-neutral-300 hover:border-sky-500/40"
    >Reload</button>
  </header>

  <ErrorBanner message={error} title="Plugin error" onDismiss={() => (error = "")} testId="plugins-error" />

  {#if !plugins.length}
    <p class="rounded-2xl border border-dashed border-neutral-800 px-4 py-10 text-center text-xs text-neutral-500">
      No plugins installed. Add a folder under <span class="font-mono">plugins/</span> with a manifest.
    </p>
  {:else}
    <ul class="space-y-2">
      {#each plugins as plugin (plugin.id)}
        <li class="rounded-2xl border border-neutral-800 bg-white/[0.02] p-4">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p class="text-sm font-medium text-neutral-100">{plugin.name}</p>
              <p class="mt-0.5 font-mono text-[10px] text-neutral-500">{plugin.id} · v{plugin.version}</p>
            </div>
            <div class="flex items-center gap-2">
              <span class={`rounded-full border px-2 py-0.5 text-[10px] uppercase ${plugin.loaded ? "border-emerald-400/30 text-emerald-200" : "border-amber-400/30 text-amber-200"}`}>
                {plugin.loaded ? "loaded" : plugin.enabled ? "blocked" : "disabled"}
              </span>
              <button type="button" disabled={busy === plugin.id} onclick={() => void toggle(plugin)} class="rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-neutral-300 disabled:opacity-40">
                {plugin.enabled ? "Disable" : "Enable"}
              </button>
            </div>
          </div>
          {#if plugin.provides?.length}
            <p class="mt-2 text-[11px] text-neutral-500">Provides: {plugin.provides.join(", ")}</p>
          {/if}
          {#if plugin.permissions?.length}
            <p class="mt-1 text-[11px] text-neutral-500">Permissions: {plugin.permissions.join(", ")}</p>
          {/if}
          {#if plugin.sandbox?.length}
            <ul class="mt-2 list-disc rounded-lg border border-rose-500/20 bg-rose-950/20 px-4 py-1.5 text-[11px] text-rose-200">
              {#each plugin.sandbox as violation}<li>{violation}</li>{/each}
            </ul>
          {:else if plugin.error}
            <p class="mt-2 text-[11px] text-rose-200">{plugin.error}</p>
          {/if}
        </li>
      {/each}
    </ul>
  {/if}

  {#if panels.length}
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4">
      <p class="text-xs font-semibold text-neutral-100">Plugin panels</p>
      <ul class="mt-2 space-y-1">
        {#each panels as panel (panel.id)}
          <li class="flex items-center gap-2">
            <a class="text-[11px] text-sky-300 underline" href={panel.url} target="_blank" rel="noreferrer">{panel.title}</a>
            <button type="button" class="rounded border border-white/10 px-2 py-0.5 text-[10px] text-neutral-300" onclick={() => (activePanel = activePanel === panel.id ? "" : panel.id)}>
              {activePanel === panel.id ? "Close" : "Open here"}
            </button>
          </li>
        {/each}
      </ul>
      {#each panels.filter((panel) => panel.id === activePanel) as panel (panel.id)}
        <iframe
          title={panel.title}
          src={panel.url}
          sandbox="allow-scripts allow-same-origin allow-forms"
          class="mt-3 h-[480px] w-full rounded-xl border border-neutral-800 bg-black"
        ></iframe>
      {/each}
    </section>
  {/if}
</section>
