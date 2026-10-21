<script lang="ts">
  import { onMount } from "svelte";
  import {
    applyProjectTemplate,
    deleteProjectTemplate,
    errorMessage,
    exportConfig,
    getProjectTemplates,
    importConfig,
    saveProjectTemplate,
    type ProjectTemplate
  } from "$lib/api";

  let {
    getOptions,
    onApply
  }: {
    getOptions: () => Record<string, unknown>;
    onApply: (options: Record<string, unknown>) => void;
  } = $props();
  let templates = $state<ProjectTemplate[]>([]);
  let name = $state("");
  let description = $state("");
  let busy = $state(false);
  let error = $state("");
  let importInput: HTMLInputElement | undefined = $state();

  async function refresh() {
    try {
      templates = await getProjectTemplates();
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function save() {
    if (!name.trim() || busy) return;
    busy = true;
    error = "";
    try {
      await saveProjectTemplate(name.trim(), description, getOptions());
      name = "";
      description = "";
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function apply(template: ProjectTemplate) {
    busy = true;
    try {
      onApply(await applyProjectTemplate(template.name));
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function remove(template: ProjectTemplate) {
    busy = true;
    try {
      await deleteProjectTemplate(template.name);
      await refresh();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      busy = false;
    }
  }

  async function exportCurrent() {
    try {
      const envelope = await exportConfig(getOptions());
      const blob = new Blob([JSON.stringify(envelope, null, 2) + "\n"], {
        type: "application/json"
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "videoflow-config.json";
      link.click();
      URL.revokeObjectURL(url);
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function importFile(event: Event) {
    const target = event.currentTarget as HTMLInputElement;
    const file = target.files?.[0];
    if (!file) return;
    try {
      const payload = JSON.parse(await file.text());
      const options = await importConfig(Number(payload.schema_version), payload.options ?? {});
      onApply(options);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      target.value = "";
    }
  }

  onMount(() => {
    void refresh();
  });
</script>

<div class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
  <div class="flex flex-wrap items-start justify-between gap-3">
    <div>
      <h2 class="text-sm font-semibold">Project templates</h2>
      <p class="mt-1 text-xs text-neutral-500">
        Save the current non-secret run configuration as a reusable template.
      </p>
    </div>
    <div class="flex gap-2">
      <button type="button" onclick={exportCurrent} class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-[10px] text-neutral-300 hover:border-sky-500/60 hover:text-sky-200">
        Export JSON
      </button>
      <input bind:this={importInput} type="file" accept=".json" onchange={importFile} class="hidden" />
      <button type="button" onclick={() => importInput?.click()} class="rounded-lg border border-neutral-700 px-2.5 py-1.5 text-[10px] text-neutral-300 hover:border-sky-500/60 hover:text-sky-200">
        Import JSON
      </button>
    </div>
  </div>

  <div class="mt-3 grid gap-2 sm:grid-cols-2">
    <input type="text" value={name} oninput={(event) => (name = event.currentTarget.value)} placeholder="Template name" class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100" />
    <input type="text" value={description} oninput={(event) => (description = event.currentTarget.value)} placeholder="Description" class="rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100" />
  </div>
  <button type="button" onclick={save} disabled={busy || !name.trim()} class="mt-2 rounded-lg border border-sky-500/40 bg-sky-500/10 px-2.5 py-1.5 text-[10px] text-sky-200 disabled:opacity-40">
    Save current config
  </button>
  {#if error}<p class="mt-2 text-[10px] text-rose-300">{error}</p>{/if}
  {#if templates.length}
    <div class="mt-3 grid gap-1.5 lg:grid-cols-2">
      {#each templates as template}
        <div class="flex items-center gap-2 rounded-lg border border-neutral-800 bg-neutral-950/60 px-2 py-1.5">
          <div class="min-w-0 flex-1">
            <p class="truncate text-[11px] text-neutral-200">{template.name}</p>
            {#if template.description}<p class="truncate text-[9px] text-neutral-500">{template.description}</p>{/if}
          </div>
          <button type="button" onclick={() => apply(template)} disabled={busy} class="text-[10px] text-sky-300 hover:text-sky-200">Apply</button>
          <button type="button" onclick={() => remove(template)} disabled={busy} class="text-[10px] text-rose-300 hover:text-rose-200">Delete</button>
        </div>
      {/each}
    </div>
  {/if}
</div>
