<script lang="ts">
  import type { TimelineData } from "$lib/api";
  import Icon from "$lib/ui/Icon.svelte";

  let {
    video,
    inactive,
    selectedClipId = "",
    selectedInactiveId = "",
    onSelectClip,
    onSelectInactive,
    onSeek,
    onToggle
  }: {
    video: TimelineData["video"];
    inactive: TimelineData["inactive"];
    selectedClipId?: string;
    selectedInactiveId?: string;
    onSelectClip: (id: string) => void;
    onSelectInactive: (id: string) => void;
    onSeek: (time: number) => void;
    onToggle: (id: string, active: boolean) => void;
  } = $props();
</script>

<div class="mx-3 mb-2 space-y-2 rounded-xl border border-neutral-800 bg-neutral-950 p-3" data-testid="timeline-mobile">
  <div class="flex items-center justify-between gap-2">
    <p class="vf-label">Timeline list</p>
    <span class="text-[length:var(--vf-text-2xs)] text-neutral-500">
      {video.length} active · {inactive.length} inactive
    </span>
  </div>
  <p class="text-[length:var(--vf-text-2xs)] text-neutral-500">
    The canvas needs a wider screen. Select a clip here, then trim or move it in the inspector below.
  </p>

  <ol class="space-y-1.5">
    {#each video as clip, index (clip.id)}
      <li class={`rounded-lg border px-2.5 py-2 ${selectedClipId === clip.id ? "border-sky-500/40 bg-sky-500/10" : "border-neutral-800 bg-neutral-900/50"}`}>
        <div class="flex items-start justify-between gap-2">
          <button type="button" class="min-w-0 flex-1 text-left" onclick={() => onSelectClip(clip.id)}>
            <span class="block truncate font-mono text-[length:var(--vf-text-xs)] text-neutral-100">{index + 1}. {clip.id}</span>
            <span class="mt-0.5 block text-[length:var(--vf-text-2xs)] text-neutral-500">
              {clip.start_sec.toFixed(2)}s → {clip.end_sec.toFixed(2)}s · {(clip.end_sec - clip.start_sec).toFixed(2)}s
            </span>
          </button>
          <button type="button" class="rounded border border-neutral-700 px-1.5 py-0.5 text-[length:var(--vf-text-2xs)] text-neutral-300" onclick={() => onSeek(clip.start_sec)} aria-label={`Seek to ${clip.id}`}>
            <Icon name="play" size={11} />
          </button>
        </div>
        <div class="mt-1.5 flex flex-wrap gap-1.5">
          <button type="button" class="rounded border border-sky-500/40 px-2 py-0.5 text-[length:var(--vf-text-2xs)] text-sky-200" onclick={() => onSelectClip(clip.id)}>Inspect</button>
          <button type="button" class="rounded border border-rose-500/30 px-2 py-0.5 text-[length:var(--vf-text-2xs)] text-rose-200" onclick={() => onToggle(clip.id, false)}>Deactivate</button>
        </div>
      </li>
    {/each}
    {#if !video.length}
      <li class="rounded-lg border border-dashed border-neutral-800 px-3 py-4 text-center text-[length:var(--vf-text-xs)] text-neutral-500">
        No active video segments. Activate an inactive segment below or re-run the timeline step.
      </li>
    {/if}
  </ol>

  {#if inactive.length}
    <div class="border-t border-neutral-800 pt-2">
      <p class="vf-label">Inactive segments</p>
      <ol class="mt-1.5 space-y-1">
        {#each inactive as item (item.id)}
          <li class={`flex items-center gap-2 rounded-lg border px-2 py-1.5 ${selectedInactiveId === item.id ? "border-rose-400/40 bg-rose-400/10" : "border-neutral-800 bg-neutral-900/50"}`}>
            <button type="button" class="min-w-0 flex-1 text-left" onclick={() => onSelectInactive(item.id)}>
              <span class="block truncate font-mono text-[length:var(--vf-text-2xs)] text-rose-200">{item.id}</span>
              <span class="block truncate text-[length:var(--vf-text-2xs)] text-neutral-500">{item.reason} · {item.video_start_sec.toFixed(1)}s</span>
            </button>
            <button type="button" class="rounded border border-sky-500/40 px-2 py-0.5 text-[length:var(--vf-text-2xs)] text-sky-200" onclick={() => onToggle(item.id, true)}>Activate</button>
          </li>
        {/each}
      </ol>
    </div>
  {/if}
</div>
