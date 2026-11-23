<script lang="ts">
  import GpuPanel from "$lib/GpuPanel.svelte";
  import IntegrationsPanel from "$lib/IntegrationsPanel.svelte";
  import SettingsPanel from "$lib/SettingsPanel.svelte";
  import StylesPanel from "$lib/StylesPanel.svelte";
  import WorkspacePanel from "$lib/WorkspacePanel.svelte";

  type SetupTab = "worker" | "styles" | "connect";

  let active = $state<SetupTab>("worker");

  const tabs: Array<{ id: SetupTab; label: string }> = [
    { id: "worker", label: "Worker GPU" },
    { id: "styles", label: "Styles & Workflows" },
    { id: "connect", label: "OpenCode & Workspace" }
  ];
</script>

<section class="space-y-4" data-testid="setup-panel">
  <div class="flex gap-1 overflow-x-auto rounded-2xl border border-neutral-800 bg-neutral-900/50 p-1.5" role="tablist" aria-label="Setup sections">
    {#each tabs as tab (tab.id)}
      <button
        type="button"
        role="tab"
        aria-selected={active === tab.id}
        onclick={() => (active = tab.id)}
        class={`shrink-0 rounded-lg px-3 py-2 text-[length:var(--vf-text-xs)] font-medium transition-colors ${
          active === tab.id
            ? "bg-sky-500/15 text-sky-100 ring-1 ring-inset ring-sky-400/20"
            : "text-neutral-400 hover:bg-white/[0.04] hover:text-neutral-100"
        }`}
      >{tab.label}</button>
    {/each}
  </div>

  {#if active === "worker"}
    <GpuPanel />
  {:else if active === "styles"}
    <StylesPanel />
  {:else}
    <div class="space-y-4">
      <WorkspacePanel />
      <IntegrationsPanel />
      <details class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
        <summary class="cursor-pointer text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">Advanced settings</summary>
        <div class="mt-4">
          <SettingsPanel />
        </div>
      </details>
    </div>
  {/if}
</section>
