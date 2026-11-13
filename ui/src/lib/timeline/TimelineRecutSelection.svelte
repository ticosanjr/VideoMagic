<script lang="ts">
  import type { TimelineData } from "$lib/api";
  type MaybeAsync = void | Promise<void>;

  let {
    inactive,
    start = $bindable(0),
    end = $bindable(0),
    editBusy = false,
    onApply,
    onActivate
  }: {
    inactive: TimelineData["inactive"][number];
    start?: number;
    end?: number;
    editBusy?: boolean;
    onApply: (id: string, start: number, end: number) => MaybeAsync;
    onActivate: (id: string) => MaybeAsync;
  } = $props();
</script>

<div data-testid="recut-selection" class="flex flex-wrap items-center justify-between gap-2 border-t border-neutral-800 px-3 py-2 text-[10px]">
  <p class="text-rose-200">Inactive <span class="font-mono">{inactive.id}</span> · {inactive.reason}</p>
  <div class="flex flex-wrap items-center gap-2">
    <label class="flex items-center gap-1 text-neutral-500">
      Start
      <input
        data-testid="recut-start"
        type="number"
        min="0"
        step="0.01"
        bind:value={start}
        disabled={editBusy}
        class="w-20 rounded border border-neutral-700 bg-neutral-950 px-1 py-0.5 font-mono text-[10px] text-neutral-200"
      />
    </label>
    <label class="flex items-center gap-1 text-neutral-500">
      End
      <input
        data-testid="recut-end"
        type="number"
        min="0"
        step="0.01"
        bind:value={end}
        disabled={editBusy}
        class="w-20 rounded border border-neutral-700 bg-neutral-950 px-1 py-0.5 font-mono text-[10px] text-neutral-200"
      />
    </label>
    <button type="button" onclick={() => void onApply(inactive.id, start, end)} disabled={editBusy} class="rounded-lg border border-rose-500/40 bg-rose-500/10 px-3 py-1 text-rose-100 disabled:opacity-40">Apply cut</button>
    <button type="button" onclick={() => void onActivate(inactive.id)} disabled={editBusy} class="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1 text-sky-200 disabled:opacity-40">Activate</button>
  </div>
</div>
