<script lang="ts">
  import type { TimelineData } from "$lib/api";

  let {
    inactive,
    onSelect,
    onActivate
  }: {
    inactive: TimelineData["inactive"];
    onSelect: (id: string) => void;
    onActivate: (id: string) => void;
  } = $props();
</script>

<div class="rounded-xl border border-neutral-800 bg-neutral-900/40 p-3" data-testid="inactive-list">
  <div class="flex items-center justify-between">
    <p class="text-[10px] uppercase tracking-wide text-neutral-500">Inactive segments</p>
    <span class="text-[9px] text-neutral-600">{inactive.length}</span>
  </div>
  <div class="mt-2 max-h-32 space-y-1 overflow-auto">
    {#each inactive as item (item.id)}
      <div class="flex items-center gap-1 rounded bg-neutral-950/60 px-1.5 py-1">
        <button type="button" onclick={() => onSelect(item.id)} class="min-w-0 flex-1 truncate text-left text-[10px] text-rose-200">{item.id} · {item.reason} · {item.video_start_sec.toFixed(1)}s</button>
        <button type="button" onclick={() => onActivate(item.id)} class="rounded px-1 text-[10px] text-sky-300 hover:text-white" aria-label={`Activate ${item.id}`}>Activate</button>
      </div>
    {/each}
    {#if !inactive.length}<p class="text-[10px] text-neutral-600">Every source segment is active.</p>{/if}
  </div>
</div>
