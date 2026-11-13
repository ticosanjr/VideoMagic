<script lang="ts">
  import type { TimelineData } from "$lib/api";
  type MaybeAsync = void | Promise<void>;

  let {
    captions,
    selectedCaption,
    draft = $bindable(""),
    busy = false,
    status = "",
    onSelect,
    onSave
  }: {
    captions: TimelineData["captions"];
    selectedCaption: number | null;
    draft?: string;
    busy?: boolean;
    status?: string;
    onSelect: (caption: TimelineData["captions"][number]) => void;
    onSave: () => MaybeAsync;
  } = $props();
</script>

<div class="rounded-xl border border-neutral-800 bg-neutral-900/40 p-3">
  <p class="text-[10px] uppercase tracking-wide text-neutral-500">Captions</p>
  <div class="mt-2 max-h-44 space-y-1 overflow-auto">
    {#each captions as caption}
      <button
        type="button"
        onclick={() => onSelect(caption)}
        class={`block w-full truncate rounded px-2 py-1 text-left text-[10px] ${selectedCaption === caption.id ? "bg-violet-500/20 text-violet-100" : "text-neutral-400 hover:bg-neutral-800/60"}`}
      >
        {caption.start_sec.toFixed(1)}s · {caption.text}
      </button>
    {/each}
    {#if !captions.length}<p class="text-[10px] text-neutral-600">No captions in this timeline.</p>{/if}
  </div>
  {#if selectedCaption !== null}
    <textarea rows="3" bind:value={draft} class="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"></textarea>
    <div class="mt-2 flex items-center gap-2">
      <button type="button" onclick={() => void onSave()} disabled={busy} class="rounded border border-violet-500/40 px-2 py-1 text-[10px] text-violet-200 disabled:opacity-40">{busy ? "Saving…" : "Save caption"}</button>
      {#if status}<span class="text-[10px] text-neutral-400">{status}</span>{/if}
    </div>
  {/if}
</div>
