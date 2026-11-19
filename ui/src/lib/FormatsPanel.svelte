<script lang="ts">
  import { onMount } from "svelte";
  import { listStyles, type StyleSummary } from "$lib/api";

  let styles = $state<StyleSummary[]>([]);
  let error = $state("");

  const formats = ["9:16", "4:5", "1:1", "16:9"];
  const grouped = $derived(
    formats.map((format) => ({
      format,
      styles: styles.filter((style) => style.aspect_ratio === format)
    }))
  );

  onMount(() => {
    void listStyles().then((value) => (styles = value)).catch((reason) => {
      error = reason instanceof Error ? reason.message : String(reason);
    });
  });
</script>

<section class="space-y-4" data-testid="formats-panel">
  <div class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
    <p class="vf-label text-sky-300/80">Setup · Formats</p>
    <h2 class="mt-1 text-[length:var(--vf-text-xl)] font-semibold text-white">Formats and aspect ratios</h2>
    <p class="mt-1 text-[length:var(--vf-text-xs)] text-neutral-400">Formats come from the style catalog. Open a style to change its aspect ratio, safe zones, caption preset, and export targets.</p>
  </div>
  {#if error}<p class="rounded-lg border border-rose-400/20 bg-rose-950/30 px-3 py-2 text-[length:var(--vf-text-xs)] text-rose-200">{error}</p>{/if}
  <div class="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
    {#each grouped as group}
      <article class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4">
        <p class="text-2xl font-semibold text-white">{group.format}</p>
        <p class="mt-1 text-[11px] uppercase tracking-wide text-neutral-500">{group.styles.length} style(s)</p>
        <ul class="mt-3 space-y-1 text-[length:var(--vf-text-xs)] text-neutral-300">
          {#each group.styles as style}<li>{style.name}</li>{/each}
        </ul>
        <a href="#styles" class="mt-3 inline-block rounded-lg border border-white/10 px-2.5 py-1 text-[11px] text-neutral-300">Edit in Styles</a>
      </article>
    {/each}
  </div>
  <div class="rounded-2xl border border-neutral-800 bg-neutral-950/70 p-4 text-[length:var(--vf-text-xs)] text-neutral-400">
    Shorts safe zones: bottom <strong class="text-neutral-200">380 px</strong> · right <strong class="text-neutral-200">140 px</strong>. Caption blocks use 3–4 words, ≤18 chars per line, and ≤2 lines.
  </div>
</section>
