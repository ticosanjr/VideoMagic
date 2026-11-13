<script lang="ts">
  import type { TimelineData } from "$lib/api";
  import Icon from "$lib/ui/Icon.svelte";

  let {
    markers,
    onSeek,
    onRemove
  }: {
    markers: TimelineData["markers"];
    onSeek: (time: number) => void;
    onRemove: (id: string) => void;
  } = $props();
</script>

<div class="rounded-xl border border-neutral-800 bg-neutral-900/40 p-3">
  <div class="flex items-center justify-between">
    <p class="text-[10px] uppercase tracking-wide text-neutral-500">Markers</p>
    <span class="text-[9px] text-neutral-600">{markers.length}</span>
  </div>
  <div class="mt-2 max-h-32 space-y-1 overflow-auto">
    {#each markers as marker}
      <div class="flex items-center gap-1 rounded bg-neutral-950/60 px-1.5 py-1">
        <button type="button" onclick={() => onSeek(marker.time_sec)} class="min-w-0 flex-1 truncate text-left text-[10px] text-sky-200">{marker.time_sec.toFixed(2)}s · {marker.label || "Marker"}</button>
        <button type="button" onclick={() => onRemove(marker.id)} class="rounded px-1 text-[10px] text-neutral-500 hover:text-rose-300" aria-label="Remove marker"><Icon name="close" size={11} /></button>
      </div>
    {/each}
    {#if !markers.length}<p class="text-[10px] text-neutral-600">No markers.</p>{/if}
  </div>
</div>
