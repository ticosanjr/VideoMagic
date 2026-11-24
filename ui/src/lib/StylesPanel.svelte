<script lang="ts">
  import { onMount } from "svelte";
  import {
    deleteStyle,
    duplicateStyle,
    exportCatalogBundle,
    getStyle,
    importCatalogBundle,
    listFormats,
    listStyles,
    listWorkflows,
    restoreStyle,
    saveStyleMarkdown,
    type CatalogBundle,
    type OutputFormat,
    type StyleSummary
  } from "$lib/api";

  let styles = $state<StyleSummary[]>([]);
  let formats = $state<OutputFormat[]>([]);
  let selected = $state("");
  let formatId = $state("");
  let creating = $state(false);
  let styleId = $state("");
  let name = $state("");
  let markdown = $state("");
  let busy = $state(false);
  let error = $state("");
  let notice = $state("");
  let workflowCount = $state(0);
  let overwrite = $state(true);
  let fileInput = $state<HTMLInputElement | null>(null);

  async function load() {
    try {
      const [styleList, workflows, formatList] = await Promise.all([
        listStyles(),
        listWorkflows(),
        listFormats()
      ]);
      styles = styleList;
      workflowCount = workflows.length;
      formats = formatList;
      if (!selected && styles.length) await open(styles[0].style_id);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    }
  }

  function feedback(reason: unknown): string {
    return reason instanceof Error ? reason.message : String(reason);
  }

  async function exportAll() {
    busy = true;
    error = "";
    try {
      const bundle = await exportCatalogBundle();
      const blob = new Blob([JSON.stringify(bundle, null, 2)], {
        type: "application/json"
      });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = "videoflow-styles-workflows.json";
      link.click();
      URL.revokeObjectURL(url);
      notice = `Exported ${bundle.styles.length} styles and ${bundle.workflows.length} workflows.`;
    } catch (reason) {
      error = feedback(reason);
    } finally {
      busy = false;
    }
  }

  async function importAll(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    busy = true;
    error = "";
    try {
      const text = (await file.text()).replace(/^\uFEFF/, "");
      const bundle = JSON.parse(text) as CatalogBundle;
      const result = await importCatalogBundle(bundle, overwrite, "");
      const skipped = result.skipped_styles + result.skipped_workflows;
      notice = `Imported ${result.imported_styles} styles and ${result.imported_workflows} workflows (${skipped} skipped).`;
      input.value = "";
      await load();
    } catch (reason) {
      error = feedback(reason);
    } finally {
      busy = false;
    }
  }

  async function open(styleId: string) {
    selected = styleId;
    try {
      const detail = await getStyle(styleId);
      name = String(detail.style.name ?? styleId);
      formatId = String(detail.style.format_id ?? "");
      markdown = detail.markdown;
      error = "";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    }
  }

  function createNew() {
    creating = true;
    selected = "";
    styleId = "meu-estilo";
    name = "Meu estilo";
    formatId = "";
    markdown = `---\nname: Meu estilo\naspect_ratio: "9:16"\ncaption_preset: youtube_bold_yellow\n---\n\n# Direção\n\nDescreva o estilo aqui.\n`;
    notice = "";
    error = "";
  }

  async function save() {
    if (!selected && !creating) return;
    busy = true;
    try {
      const result = await saveStyleMarkdown({
        style_id: creating ? styleId : selected,
        name,
        markdown_content: markdown,
        format_id: formatId,
        overwrite: true
      });
      selected = result.style_id;
      creating = false;
      notice = "Style saved.";
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = false;
    }
  }

  async function restore() {
    if (!selected) return;
    busy = true;
    try {
      await restoreStyle(selected);
      notice = "Seed style restored.";
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = false;
    }
  }

  async function duplicate() {
    if (!selected) return;
    busy = true;
    try {
      const result = await duplicateStyle(selected, { name: `${name} copy` });
      notice = `Created ${result.style_id}.`;
      selected = result.style_id;
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = false;
    }
  }

  async function remove() {
    if (!selected) return;
    busy = true;
    try {
      await deleteStyle(selected);
      selected = "";
      notice = "Style deleted.";
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = false;
    }
  }

  onMount(() => void load());
</script>

<section class="space-y-4" data-testid="styles-panel">
  <div class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
    <p class="vf-label text-sky-300/80">Setup · Styles</p>
    <h2 class="mt-1 text-[length:var(--vf-text-xl)] font-semibold text-white">Style catalog</h2>
    <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-400">Edit the Markdown style, duplicate it, or delete custom styles. Presets and MCP agents read the same catalog.</p>
    <p class="mt-2 text-[length:var(--vf-text-xs)] text-neutral-500">{styles.length} styles · {workflowCount} workflows</p>
    <div class="mt-3 flex flex-wrap items-center gap-2">
      <button type="button" disabled={busy} onclick={() => void exportAll()} class="rounded-lg border border-sky-400/25 bg-sky-500/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-sky-100 disabled:opacity-40">Export all (JSON)</button>
      <button type="button" disabled={busy} onclick={() => fileInput?.click()} class="rounded-lg border border-white/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-200 disabled:opacity-40">Import all (JSON)</button>
      <input bind:this={fileInput} type="file" accept=".json,application/json" class="hidden" onchange={importAll} />
      <label class="flex items-center gap-2 text-[length:var(--vf-text-xs)] text-neutral-400">
        <input type="checkbox" bind:checked={overwrite} />
        Overwrite existing
      </label>
    </div>
  </div>
  {#if error}<p class="rounded-lg border border-rose-400/20 bg-rose-950/30 px-3 py-2 text-[length:var(--vf-text-xs)] text-rose-200">{error}</p>{/if}
  {#if notice}<p class="rounded-lg border border-emerald-400/20 bg-emerald-950/30 px-3 py-2 text-[length:var(--vf-text-xs)] text-emerald-200">{notice}</p>{/if}
  <div class="grid gap-4 xl:grid-cols-[320px_1fr]">
    <aside class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-3">
      <ul class="space-y-1">
        {#each styles as style}
          <li>
            <button type="button" onclick={() => void open(style.style_id)} class={`w-full rounded-lg px-3 py-2 text-left text-[length:var(--vf-text-xs)] ${selected === style.style_id ? "bg-sky-500/15 text-sky-100" : "text-neutral-300 hover:bg-white/[0.04]"}`}>
              <span class="block font-medium">{style.name}</span>
              <span class="block font-mono text-[10px] text-neutral-500">{style.style_id} · {style.format_id || style.aspect_ratio || "auto"}</span>
            </button>
          </li>
        {/each}
      </ul>
    </aside>
    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
      {#if selected || creating}
        <div class="flex flex-wrap items-center gap-2">
          {#if creating}
            <input bind:value={styleId} class="w-40 rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 font-mono text-[11px] text-neutral-200" />
          {:else}
            <input value={selected} disabled class="w-40 rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 font-mono text-[11px] text-neutral-400" />
          {/if}
          <input bind:value={name} class="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[length:var(--vf-text-sm)] text-neutral-100" />
          <select bind:value={formatId} title="Output format linked to this style" class="rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[length:var(--vf-text-xs)] text-neutral-200">
            <option value="">No linked format</option>
            {#each formats as format}
              <option value={format.format_id}>{format.name} · {format.aspect_ratio}</option>
            {/each}
          </select>
          <button type="button" disabled={busy} onclick={() => void save()} class="rounded-lg border border-emerald-400/25 bg-emerald-500/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-emerald-100 disabled:opacity-40">Save</button>
          <button type="button" disabled={busy || creating} onclick={() => void duplicate()} class="rounded-lg border border-white/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-300">Duplicate</button>
          <button type="button" disabled={busy || creating} title="Restore the shipped seed version" onclick={() => void restore()} class="rounded-lg border border-white/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-300">Restore seed</button>
          <button type="button" disabled={busy || creating} title="Delete this custom style" onclick={() => void remove()} class="rounded-lg border border-rose-400/20 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-rose-200">Delete</button>
        </div>
        <textarea bind:value={markdown} spellcheck="false" class="mt-3 h-[55vh] w-full rounded-xl border border-white/10 bg-black/40 p-3 font-mono text-[length:var(--vf-text-xs)] leading-5 text-neutral-200"></textarea>
      {:else}
        <p class="text-[length:var(--vf-text-sm)] text-neutral-500">Select a style to edit.</p>
      {/if}
    </article>
  </div>
</section>
