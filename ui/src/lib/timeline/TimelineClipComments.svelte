<script lang="ts">
  import type { TimelineComment, TimelineData, TimelineOverlay } from "$lib/api";
  import Icon from "$lib/ui/Icon.svelte";
  type MaybeAsync = void | Promise<void>;

  let {
    comments,
    overlays,
    clip,
    fps,
    commentText = $bindable(""),
    commentBusy = false,
    onAddComment,
    onRemoveComment,
    onRemoveOverlay
  }: {
    comments: TimelineComment[];
    overlays: TimelineOverlay[];
    clip: TimelineData["video"][number] | null;
    fps: number;
    commentText?: string;
    commentBusy?: boolean;
    onAddComment: () => MaybeAsync;
    onRemoveComment: (id: string) => MaybeAsync;
    onRemoveOverlay: (id: string) => MaybeAsync;
  } = $props();
</script>

<div class="rounded-xl border border-neutral-800 bg-neutral-900/40 p-3">
  <div class="flex items-center justify-between">
    <p class="text-[10px] uppercase tracking-wide text-neutral-500">Clip comments</p>
    <span class="text-[9px] text-neutral-600">{comments.length}</span>
  </div>
  <p class="mt-1 text-[10px] text-neutral-600">{clip ? clip.id : "Select a clip to comment."}</p>
  <div class="mt-2 max-h-32 space-y-1 overflow-auto">
    {#each comments as comment}
      <div class="flex items-start gap-1 rounded bg-neutral-950/60 px-1.5 py-1">
        <p class="min-w-0 flex-1 text-[10px] text-neutral-300">{comment.text}</p>
        <button type="button" onclick={() => void onRemoveComment(comment.id)} class="rounded px-1 text-[10px] text-neutral-500 hover:text-rose-300" aria-label="Remove comment"><Icon name="close" size={11} /></button>
      </div>
    {/each}
    {#if !comments.length}<p class="text-[10px] text-neutral-600">No comments for this clip.</p>{/if}
  </div>
  <form class="mt-2 flex gap-1" onsubmit={(event) => { event.preventDefault(); void onAddComment(); }}>
    <input bind:value={commentText} disabled={!clip} placeholder="Add a note…" class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-1.5 py-0.5 text-[10px] text-neutral-200" />
    <button type="submit" disabled={!clip || commentBusy} class="rounded border border-sky-500/40 px-2 py-0.5 text-[10px] text-sky-200 disabled:opacity-40">Add</button>
  </form>
  <div class="mt-3 border-t border-neutral-800 pt-2">
    <p class="text-[10px] uppercase tracking-wide text-neutral-500">Overlays</p>
    <div class="mt-1 space-y-1">
      {#each overlays as overlay (overlay.overlay_id)}
        <div class="flex items-center gap-1 rounded bg-neutral-950/60 px-1.5 py-1">
          <p class="min-w-0 flex-1 truncate text-[10px] text-neutral-300">{overlay.path.split("/").pop()} · {(overlay.start_frame / Math.max(1, fps)).toFixed(2)}s</p>
          <button type="button" onclick={() => void onRemoveOverlay(overlay.overlay_id)} class="rounded px-1 text-[10px] text-neutral-500 hover:text-rose-300" aria-label="Remove overlay"><Icon name="close" size={11} /></button>
        </div>
      {/each}
      {#if !overlays.length}<p class="text-[10px] text-neutral-600">Drag an asset from the rail onto the timeline.</p>{/if}
    </div>
  </div>
</div>
