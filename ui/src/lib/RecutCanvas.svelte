<script lang="ts">
  import type { TimelineData, TimelineInactive } from "$lib/api";

  let {
    timeline,
    selectedId = "",
    busy = false,
    onselect,
    ontoggle
  }: {
    timeline: TimelineData;
    selectedId?: string;
    busy?: boolean;
    onselect: (kind: "active" | "inactive", id: string) => void;
    ontoggle: (id: string, active: boolean) => void;
  } = $props();

  let zoom = $state(70);
  let scroller = $state<HTMLDivElement | null>(null);

  const sourceDuration = $derived(
    Math.max(
      1,
      timeline.source_duration_sec ||
        Math.max(
          0,
          ...timeline.video.map((clip) => clip.source_end_sec ?? 0),
          ...timeline.inactive.map((item) => item.video_end_sec)
        )
    )
  );
  const width = $derived(Math.max(900, sourceDuration * zoom + 32));
  const step = $derived(zoom >= 100 ? 1 : zoom >= 50 ? 2 : zoom >= 24 ? 5 : 10);

  function activeVideoStart(clip: TimelineData["video"][number]): number {
    return clip.source_start_sec ?? (clip.source_in_frame ?? 0) / Math.max(1, timeline.fps);
  }
  function activeVideoEnd(clip: TimelineData["video"][number]): number {
    return clip.source_end_sec ?? (clip.source_out_frame ?? 0) / Math.max(1, timeline.fps);
  }
  function activeAudioStart(clip: TimelineData["audio"][number]): number {
    return clip.source_in_sec ?? clip.start_sec;
  }
  function activeAudioEnd(clip: TimelineData["audio"][number]): number {
    return clip.source_out_sec ?? clip.end_sec;
  }
  function widthFor(start: number, end: number): number {
    return Math.max(12, (Math.max(start, end) - start) * zoom);
  }
  function leftFor(start: number): number {
    return 8 + start * zoom;
  }

  const videoActive = $derived(timeline.video);
  const audioActive = $derived(timeline.audio);
  const inactive = $derived< TimelineInactive[]>(timeline.inactive ?? []);

  function reasonLabel(reason: string): string {
    if (reason === "silence") return "silence";
    if (reason === "retake") return "retake";
    return "manual";
  }
</script>

<div class="overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-950" data-testid="recut-canvas">
  <div class="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-800 px-3 py-2">
    <div class="flex flex-wrap items-center gap-2 text-[10px] text-neutral-400">
      <span class="flex items-center gap-1"><span class="h-2 w-3 rounded-sm border border-sky-400 bg-sky-500/30"></span>active</span>
      <span class="flex items-center gap-1"><span class="h-2 w-3 rounded-sm border border-rose-400 bg-rose-500/30"></span>inactive</span>
      <span class="text-neutral-600">{inactive.length} inactive segment(s)</span>
    </div>
    <label class="flex items-center gap-2 text-[10px] text-neutral-500">
      Zoom
      <input type="range" min="18" max="220" step="1" bind:value={zoom} class="w-24 accent-sky-400" />
      <span class="w-8 text-right font-mono text-neutral-400">{Math.round(zoom)}</span>
    </label>
  </div>

  <div bind:this={scroller} class="overflow-x-auto">
    <div class="relative h-[190px] min-w-full" style={`width:${width}px`}>
      <div class="absolute left-0 right-0 top-0 h-6 border-b border-neutral-800 bg-neutral-900/60">
        {#each Array.from({ length: Math.floor(sourceDuration / step) + 2 }, (_, index) => index * step) as second}
          <span class="absolute top-1 font-mono text-[8px] text-neutral-600" style={`left:${leftFor(second)}px`}>{second}s</span>
          <span class="absolute top-0 h-2 border-l border-neutral-700" style={`left:${leftFor(second)}px`}></span>
        {/each}
      </div>

      <div class="absolute left-0 right-0 top-6 h-[64px] border-b border-neutral-800">
        <span class="absolute left-1 top-1 z-10 text-[8px] font-bold text-neutral-500">V1 · VIDEO</span>
        {#each videoActive as clip (clip.id)}
          <button
            type="button"
            data-testid={`recut-active-${clip.id}`}
            onclick={() => onselect("active", clip.id)}
            ondblclick={() => ontoggle(clip.id, false)}
            disabled={busy}
            title="Active clip. Double-click to deactivate."
            class={`absolute top-7 h-8 overflow-hidden rounded border px-1 text-left text-[9px] ${selectedId === clip.id ? "border-sky-200 bg-sky-500/40 text-white ring-1 ring-sky-200" : "border-sky-400/70 bg-sky-500/20 text-sky-100 hover:bg-sky-500/30"}`}
            style={`left:${leftFor(activeVideoStart(clip))}px;width:${widthFor(activeVideoStart(clip), activeVideoEnd(clip))}px`}
          >{clip.id}</button>
        {/each}
        {#each inactive as item (item.id)}
          <button
            type="button"
            data-testid={`recut-inactive-${item.id}`}
            onclick={() => onselect("inactive", item.id)}
            ondblclick={() => ontoggle(item.id, true)}
            disabled={busy}
            title={`Inactive (${reasonLabel(item.reason)}). Double-click to activate.`}
            class={`absolute top-7 h-8 overflow-hidden rounded border px-1 text-left text-[9px] ${selectedId === item.id ? "border-rose-200 bg-rose-500/40 text-white ring-1 ring-rose-200" : "border-rose-400/70 bg-rose-500/20 text-rose-100 hover:bg-rose-500/30"}`}
            style={`left:${leftFor(item.video_start_sec)}px;width:${widthFor(item.video_start_sec, item.video_end_sec)}px`}
          >{item.id} · {reasonLabel(item.reason)}</button>
        {/each}
      </div>

      <div class="absolute left-0 right-0 top-[94px] h-[54px] border-b border-neutral-800">
        <span class="absolute left-1 top-1 z-10 text-[8px] font-bold text-neutral-500">A1 · DIALOGUE</span>
        {#each audioActive as clip (clip.id)}
          <button
            type="button"
            onclick={() => onselect("active", clip.id)}
            disabled={busy}
            title="Active audio clip."
            class="absolute top-6 h-7 overflow-hidden rounded border border-sky-400/60 bg-sky-500/15 px-1 text-left text-[8px] text-sky-100"
            style={`left:${leftFor(activeAudioStart(clip))}px;width:${widthFor(activeAudioStart(clip), activeAudioEnd(clip))}px`}
          >{clip.id}</button>
        {/each}
        {#each inactive as item (item.id)}
          <button
            type="button"
            onclick={() => onselect("inactive", item.id)}
            disabled={busy}
            title={`Inactive audio (${reasonLabel(item.reason)}).`}
            class="absolute top-6 h-7 overflow-hidden rounded border border-rose-400/60 bg-rose-500/15 px-1 text-left text-[8px] text-rose-100"
            style={`left:${leftFor(item.audio_start_sec)}px;width:${widthFor(item.audio_start_sec, item.audio_end_sec)}px`}
          >{item.id}</button>
        {/each}
      </div>

      <p class="absolute bottom-2 left-2 text-[9px] text-neutral-600">
        Source time · {sourceDuration.toFixed(1)}s · double-click a block to toggle it
      </p>
    </div>
  </div>
</div>
