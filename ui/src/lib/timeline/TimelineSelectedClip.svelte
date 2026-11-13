<script lang="ts">
  import type { TimelineData } from "$lib/api";

  let {
    clip,
    revision,
    start = $bindable(0),
    end = $bindable(0),
    delta = $bindable(1),
    editBusy = false,
    editStatus = "",
    onTrim,
    onMove
  }: {
    clip: TimelineData["video"][number] | null;
    revision: number;
    start?: number;
    end?: number;
    delta?: number;
    editBusy?: boolean;
    editStatus?: string;
    onTrim: () => void;
    onMove: () => void;
  } = $props();
</script>

<div class="rounded-xl border border-neutral-800 bg-neutral-900/40 p-3">
  <div class="flex items-center justify-between">
    <p class="text-[10px] uppercase tracking-wide text-neutral-500">Selected clip</p>
    <span class="font-mono text-[10px] text-neutral-600">rev {revision}</span>
  </div>
  {#if clip}
    <p class="mt-1 break-all font-mono text-[11px] text-sky-200">{clip.id}</p>
    <div class="mt-2 grid grid-cols-2 gap-2">
      <label class="text-[10px] text-neutral-400">Timeline in
        <input type="number" min="0" step="0.01" bind:value={start} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
      </label>
      <label class="text-[10px] text-neutral-400">Timeline out
        <input type="number" min="0" step="0.01" bind:value={end} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
      </label>
    </div>
    <div class="mt-2 flex flex-wrap items-end gap-2">
      <button type="button" onclick={onTrim} disabled={editBusy} class="rounded border border-sky-500/40 px-2 py-1 text-[10px] text-sky-300 disabled:opacity-40">Trim</button>
      <label class="text-[10px] text-neutral-400">Move (s)
        <input type="number" step="0.1" bind:value={delta} class="mt-1 block w-20 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
      </label>
      <button type="button" onclick={onMove} disabled={editBusy} class="rounded border border-neutral-600 px-2 py-1 text-[10px] text-neutral-300 disabled:opacity-40">Move</button>
    </div>
    <p class="mt-2 text-[10px] text-neutral-500">
      Transition: {clip.transition ?? "cut"} · keyframes: {clip.keyframes ?? 0} · zoom {clip.zoom?.toFixed(2) ?? "1.00"}
    </p>
  {:else}
    <p class="mt-2 text-[10px] text-neutral-500">Select a clip on the canvas to inspect and edit it.</p>
  {/if}
  {#if editStatus}<p class="mt-1 text-[10px] text-amber-300">{editStatus}</p>{/if}
</div>
