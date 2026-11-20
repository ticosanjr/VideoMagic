<script lang="ts">
  import { onMount } from "svelte";
  import {
    deleteFormat,
    duplicateFormat,
    listFormats,
    saveFormat,
    type OutputFormat
  } from "$lib/api";

  type Draft = OutputFormat & { new?: boolean };

  let formats = $state<OutputFormat[]>([]);
  let selected = $state("");
  let draft = $state<Draft | null>(null);
  let busy = $state(false);
  let error = $state("");
  let notice = $state("");

  const empty = (): Draft => ({
    format_id: "meu-formato",
    name: "Meu formato",
    aspect_ratio: "9:16",
    width: 1080,
    height: 1920,
    fps: 30,
    safe_zones: { bottom_px: 380, right_px: 140 },
    caption_preset: "youtube_bold_yellow",
    platforms: [],
    export_targets: ["mp4_short"],
    description: "",
    builtin: false,
    new: true
  });

  async function load() {
    try {
      formats = await listFormats();
      if (!selected && formats.length) choose(formats[0]);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    }
  }

  function choose(item: OutputFormat) {
    selected = item.format_id;
    draft = { ...item, safe_zones: { ...item.safe_zones }, new: false };
    notice = "";
    error = "";
  }

  function createNew() {
    selected = "";
    draft = empty();
    notice = "";
    error = "";
  }

  async function save() {
    if (!draft) return;
    busy = true;
    try {
      const saved = await saveFormat({
        format_id: draft.format_id,
        name: draft.name,
        aspect_ratio: draft.aspect_ratio,
        width: Number(draft.width),
        height: Number(draft.height),
        fps: Number(draft.fps),
        safe_zones: draft.safe_zones,
        caption_preset: draft.caption_preset,
        platforms: draft.platforms,
        export_targets: draft.export_targets,
        description: draft.description
      });
      notice = "Format saved.";
      await load();
      choose(saved);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = false;
    }
  }

  async function duplicate() {
    if (!draft) return;
    busy = true;
    try {
      const item = await duplicateFormat(draft.format_id, { name: `${draft.name} copy` });
      notice = "Format duplicated.";
      await load();
      choose(item);
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = false;
    }
  }

  async function remove() {
    if (!draft) return;
    busy = true;
    try {
      await deleteFormat(draft.format_id);
      selected = "";
      draft = null;
      notice = "Format deleted.";
      await load();
    } catch (reason) {
      error = reason instanceof Error ? reason.message : String(reason);
    } finally {
      busy = false;
    }
  }

  function applyPreset(ratio: Draft["aspect_ratio"]) {
    if (!draft) return;
    const size = { "9:16": [1080, 1920], "4:5": [1080, 1350], "1:1": [1080, 1080], "16:9": [1920, 1080] }[ratio];
    draft = { ...draft, aspect_ratio: ratio, width: size[0], height: size[1] };
  }

  onMount(() => void load());
</script>

<section class="space-y-4" data-testid="formats-panel">
  <div class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div>
        <p class="vf-label text-sky-300/80">Setup · Formats</p>
        <h2 class="mt-1 text-[length:var(--vf-text-xl)] font-semibold text-white">Output formats</h2>
        <p class="mt-1 max-w-3xl text-[length:var(--vf-text-xs)] text-neutral-400">Aspect ratio, resolution, safe zones, caption preset, and export targets. Styles and Shorts use these presets.</p>
      </div>
      <button type="button" onclick={createNew} class="rounded-lg border border-sky-400/25 bg-sky-500/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-sky-100">New format</button>
    </div>
  </div>
  {#if error}<p class="rounded-lg border border-rose-400/20 bg-rose-950/30 px-3 py-2 text-[length:var(--vf-text-xs)] text-rose-200">{error}</p>{/if}
  {#if notice}<p class="rounded-lg border border-emerald-400/20 bg-emerald-950/30 px-3 py-2 text-[length:var(--vf-text-xs)] text-emerald-200">{notice}</p>{/if}
  <div class="grid gap-4 xl:grid-cols-[360px_1fr]">
    <aside class="grid gap-2 sm:grid-cols-2 xl:grid-cols-1">
      {#each formats as item}
        <button type="button" onclick={() => choose(item)} class={`rounded-2xl border p-3 text-left ${selected === item.format_id ? "border-sky-400/40 bg-sky-500/10" : "border-neutral-800 bg-neutral-950/70 hover:border-white/20"}`}>
          <div class="flex items-start justify-between gap-2">
            <span class="text-[length:var(--vf-text-sm)] font-semibold text-neutral-100">{item.name}</span>
            {#if item.builtin}<span class="rounded-full border border-white/10 px-1.5 py-0.5 text-[9px] uppercase text-neutral-500">built-in</span>{/if}
          </div>
          <p class="mt-1 font-mono text-[10px] text-neutral-500">{item.format_id}</p>
          <div class="mt-3 flex items-end justify-between gap-2">
            <span class="text-[length:var(--vf-text-xs)] text-neutral-300">{item.aspect_ratio} · {item.width}×{item.height}</span>
            <span class="text-[10px] text-neutral-500">{item.fps} fps</span>
          </div>
        </button>
      {/each}
    </aside>
    <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
      {#if draft}
        {#if draft.builtin}
          <p class="mb-3 rounded-lg border border-amber-400/20 bg-amber-950/20 px-3 py-2 text-[11px] text-amber-200">Built-in formats are read-only. Duplicate to customize.</p>
        {/if}
        <fieldset disabled={draft.builtin} class="border-0 p-0">
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <label class="text-[11px] text-neutral-500">Format id<input bind:value={draft.format_id} disabled={!draft.new} class="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 font-mono text-[11px] text-neutral-200" /></label>
          <label class="text-[11px] text-neutral-500">Name<input bind:value={draft.name} class="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[11px] text-neutral-200" /></label>
          <label class="text-[11px] text-neutral-500">Aspect ratio<select bind:value={draft.aspect_ratio} onchange={() => draft && applyPreset(draft.aspect_ratio)} class="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[11px] text-neutral-200">{#each ["9:16","4:5","1:1","16:9"] as ratio}<option value={ratio}>{ratio}</option>{/each}</select></label>
          <label class="text-[11px] text-neutral-500" title="Output width in pixels; must match the aspect ratio">Width<input type="number" bind:value={draft.width} class="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[11px] text-neutral-200" /></label>
          <label class="text-[11px] text-neutral-500" title="Output height in pixels; must match the aspect ratio">Height<input type="number" bind:value={draft.height} class="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[11px] text-neutral-200" /></label>
          <label class="text-[11px] text-neutral-500">FPS<input type="number" bind:value={draft.fps} class="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[11px] text-neutral-200" /></label>
          <label class="text-[11px] text-neutral-500" title="Reserved UI area at the bottom; Shorts default is 380 px">Bottom safe zone (px)<input type="number" bind:value={draft.safe_zones.bottom_px} class="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[11px] text-neutral-200" /></label>
          <label class="text-[11px] text-neutral-500" title="Reserved action rail on the right; Shorts default is 140 px">Right safe zone (px)<input type="number" bind:value={draft.safe_zones.right_px} class="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[11px] text-neutral-200" /></label>
          <label class="text-[11px] text-neutral-500">Caption preset<input bind:value={draft.caption_preset} class="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[11px] text-neutral-200" /></label>
        </div>
        <div class="mt-3 grid gap-3 sm:grid-cols-2">
          <label class="text-[11px] text-neutral-500">Platforms (comma separated)<input value={draft.platforms.join(", ")} oninput={(event) => draft && (draft.platforms = event.currentTarget.value.split(",").map((item) => item.trim()).filter(Boolean))} class="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[11px] text-neutral-200" /></label>
          <label class="text-[11px] text-neutral-500">Export targets (comma separated)<input value={draft.export_targets.join(", ")} oninput={(event) => draft && (draft.export_targets = event.currentTarget.value.split(",").map((item) => item.trim()).filter(Boolean))} class="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[11px] text-neutral-200" /></label>
        </div>
        <label class="mt-3 block text-[11px] text-neutral-500">Description<textarea bind:value={draft.description} class="mt-1 h-20 w-full rounded-lg border border-white/10 bg-black/30 px-2.5 py-2 text-[11px] text-neutral-200"></textarea></label>
        </fieldset>
        <div class="mt-3 flex flex-wrap gap-2">
          <button type="button" disabled={busy || draft.builtin} onclick={() => void save()} class="rounded-lg border border-emerald-400/25 bg-emerald-500/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-emerald-100 disabled:opacity-40">Save</button>
          <button type="button" disabled={busy || draft.new} onclick={() => void duplicate()} class="rounded-lg border border-white/10 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-neutral-300">Duplicate</button>
          <button type="button" disabled={busy || draft.new || draft.builtin} onclick={() => void remove()} class="rounded-lg border border-rose-400/20 px-3 py-1.5 text-[length:var(--vf-text-xs)] text-rose-200">Delete</button>
        </div>
        <div class="mt-4 rounded-xl border border-white/10 bg-black/20 p-3">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Preview · {draft.aspect_ratio}</p>
          <div class="mt-2 flex justify-center">
            <div class="relative rounded border border-sky-400/30 bg-sky-500/10" style={`width:${Math.min(240, 240 * draft.width / Math.max(draft.width, draft.height))}px;height:${Math.min(240, 240 * draft.height / Math.max(draft.width, draft.height))}px`}>
              <span class="absolute bottom-0 left-0 right-0 border-t border-dashed border-amber-300/60 bg-amber-300/10" style={`height:${Math.max(8, Math.min(70, draft.safe_zones.bottom_px / 6))}px`}></span>
              <span class="absolute right-0 top-0 bottom-0 border-l border-dashed border-rose-300/60 bg-rose-300/10" style={`width:${Math.max(6, Math.min(50, draft.safe_zones.right_px / 4))}px`}></span>
            </div>
          </div>
        </div>
      {:else}
        <p class="text-[length:var(--vf-text-sm)] text-neutral-500">Select a format or create a new one.</p>
      {/if}
    </article>
  </div>
</section>
