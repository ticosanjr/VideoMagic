<script lang="ts">
  import { onMount } from "svelte";
  import {
    deleteStyle,
    duplicateStyle,
    getStyle,
    listStyles,
    saveStyleMarkdown,
    type StyleSummary
  } from "$lib/api";

  let styles = $state<StyleSummary[]>([]);
  let selected = $state("");
  let name = $state("");
  let markdown = $state("");
  let busy = $state(false);
  let error = $state("");
  let notice = $state("");

  async function load() {
    try {
      styles = await listStyles();
      if (!selected && styles.length) await open(styles[0].style_id);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    }
  }

  async function open(styleId: string) {
    selected = styleId;
    try {
      const detail = await getStyle(styleId);
      name = String(detail.style.name ?? styleId);
      markdown = detail.markdown;
      error = "";
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    }
  }

  async function save() {
    if (!selected) return;
    busy = true;
    try {
      await saveStyleMarkdown({
        style_id: selected,
        name,
        markdown_content: markdown,
        overwrite: true
      });
      notice = "Style saved.";
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
              <span class="block font-mono text-[10px] text-neutral-500">{style.style_id} · {style.aspect_ratio || "auto"}</span>
            </button>
          </li>
        {/each}
      </ul>
    </aside>
    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
      {#if selected}
        <div class="flex flex-wrap items-center gap-2">
          <input bind:value={name} class="min-w-0 flex-1 rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[length:var(--vf-text-sm)] text-neutral-100" />
          <button type="button" disabled={busy} onclick={() => void save()} class="rounded-lg border border-emerald-400/25 bg-emerald-500/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-emerald-100 disabled:opacity-40">Save</button>
          <button type="button" disabled={busy} onclick={() => void duplicate()} class="rounded-lg border border-white/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-300">Duplicate</button>
          <button type="button" disabled={busy} onclick={() => void remove()} class="rounded-lg border border-rose-400/20 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-rose-200">Delete</button>
        </div>
        <textarea bind:value={markdown} spellcheck="false" class="mt-3 h-[55vh] w-full rounded-xl border border-white/10 bg-black/40 p-3 font-mono text-[length:var(--vf-text-xs)] leading-5 text-neutral-200"></textarea>
      {:else}
        <p class="text-[length:var(--vf-text-sm)] text-neutral-500">Select a style to edit.</p>
      {/if}
    </article>
  </div>
</section>
