<script lang="ts">
  import { onDestroy } from "svelte";
  import { jobFrameUrl, type TimelineData, type TimelineInactive } from "$lib/api";

  let {
    timeline,
    jobId = "",
    zoom = $bindable(70),
    selectedId = "",
    busy = false,
    playhead = 0,
    waveforms = {},
    tracks = {},
    onselect,
    ontoggle,
    ontrim,
    onseek,
    onToggleTrack
  }: {
    timeline: TimelineData;
    jobId?: string;
    zoom?: number;
    selectedId?: string;
    busy?: boolean;
    playhead?: number;
    waveforms?: Record<string, number[]>;
    onselect: (kind: "active" | "inactive", id: string) => void;
    ontoggle: (id: string, active: boolean) => void;
    ontrim: (id: string, start: number, end: number) => void;
    onseek?: (sourceSec: number) => void;
    tracks?: Record<string, { muted: boolean; solo: boolean; locked: boolean }>;
    onToggleTrack?: (track: string, key: "muted" | "solo" | "locked") => void;
  } = $props();

  const HEADER = 88;

  let scroller = $state<HTMLDivElement | null>(null);
  let drag = $state<{
    id: string;
    edge: "start" | "end";
    originX: number;
    start: number;
    end: number;
    startMin: number;
    endMax: number;
  } | null>(null);
  let draft = $state<{ id: string; start: number; end: number } | null>(null);
  let suppressClick = false;
  let hover = $state<{ x: number; time: number } | null>(null);
  let hoverFrame = $state("");
  let hoverTimer: ReturnType<typeof setTimeout> | undefined;

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
  const width = $derived(Math.max(420, HEADER + sourceDuration * zoom + 32));
  const step = $derived(
    zoom >= 200 ? 1 : zoom >= 110 ? 2 : zoom >= 50 ? 5 : zoom >= 20 ? 10 : zoom >= 8 ? 30 : 60
  );

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
  function wavePoints(peaks: number[]): string {
    if (peaks.length < 2) return "";
    const points: string[] = [];
    for (let index = 0; index < peaks.length; index += 1) {
      points.push(`${(index / (peaks.length - 1)) * 100},${50 - Math.max(0.02, peaks[index]) * 42}`);
    }
    for (let index = peaks.length - 1; index >= 0; index -= 1) {
      points.push(`${(index / (peaks.length - 1)) * 100},${50 + Math.max(0.02, peaks[index]) * 42}`);
    }
    return points.join(" ");
  }

  function widthFor(start: number, end: number): number {
    return Math.max(12, (Math.max(start, end) - start) * zoom);
  }
  function leftFor(start: number): number {
    return HEADER + start * zoom;
  }

  const videoActive = $derived(timeline.video);
  const audioActive = $derived(timeline.audio);
  const inactive = $derived< TimelineInactive[]>(timeline.inactive ?? []);

  function reasonLabel(reason: string): string {
    if (reason === "silence") return "silence";
    if (reason === "retake") return "retake";
    return "manual";
  }

  const frameSec = $derived(1 / Math.max(1, timeline.fps));

  function displayStart(item: TimelineInactive): number {
    return draft?.id === item.id ? draft.start : item.video_start_sec;
  }
  function displayEnd(item: TimelineInactive): number {
    return draft?.id === item.id ? draft.end : item.video_end_sec;
  }
  function adjacentBounds(item: TimelineInactive): { startMin: number; endMax: number } {
    const epsilon = frameSec / 2;
    const before = timeline.video
      .filter((clip) => {
        return activeVideoEnd(clip) <= item.video_start_sec + epsilon;
      })
      .sort((left, right) => activeVideoEnd(right) - activeVideoEnd(left))[0];
    const after = timeline.video
      .filter((clip) => {
        return activeVideoStart(clip) >= item.video_end_sec - epsilon;
      })
      .sort((left, right) => activeVideoStart(left) - activeVideoStart(right))[0];
    const startMin =
      before && Math.abs(activeVideoEnd(before) - item.video_start_sec) <= epsilon
        ? activeVideoStart(before) + frameSec
        : item.video_start_sec;
    const endMax =
      after && Math.abs(activeVideoStart(after) - item.video_end_sec) <= epsilon
        ? activeVideoEnd(after) - frameSec
        : item.video_end_sec;
    return { startMin, endMax };
  }

  function beginTrim(
    event: PointerEvent,
    item: TimelineInactive,
    edge: "start" | "end"
  ) {
    if (busy) return;
    event.preventDefault();
    event.stopPropagation();
    const bounds = adjacentBounds(item);
    drag = {
      id: item.id,
      edge,
      originX: event.clientX,
      start: item.video_start_sec,
      end: item.video_end_sec,
      ...bounds
    };
    draft = { id: item.id, start: item.video_start_sec, end: item.video_end_sec };
    suppressClick = false;
    window.addEventListener("pointermove", moveTrim);
    window.addEventListener("pointerup", finishTrim, { once: true });
    window.addEventListener("pointercancel", finishTrim, { once: true });
  }

  function moveTrim(event: PointerEvent) {
    if (!drag) return;
    const delta = (event.clientX - drag.originX) / zoom;
    if (Math.abs(delta) > 0.002) suppressClick = true;
    if (drag.edge === "start") {
      draft = {
        id: drag.id,
        start: Math.min(
          drag.end - frameSec,
          Math.max(drag.startMin, drag.start + delta)
        ),
        end: drag.end
      };
    } else {
      draft = {
        id: drag.id,
        start: drag.start,
        end: Math.max(
          drag.start + frameSec,
          Math.min(drag.endMax, drag.end + delta)
        )
      };
    }
  }

  function finishTrim() {
    window.removeEventListener("pointermove", moveTrim);
    const current = drag;
    const value = draft;
    drag = null;
    draft = null;
    if (
      current &&
      value &&
      (Math.abs(value.start - current.start) > 0.0005 ||
        Math.abs(value.end - current.end) > 0.0005)
    ) {
      ontrim(current.id, value.start, value.end);
    }
  }

  function selectBlock(kind: "active" | "inactive", id: string) {
    if (suppressClick) {
      suppressClick = false;
      return;
    }
    onselect(kind, id);
  }

  function seekFromEvent(event: MouseEvent) {
    if (!onseek) return;
    const element = event.currentTarget as HTMLElement | null;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const value = Math.max(
      0,
      Math.min(sourceDuration, (event.clientX - rect.left - HEADER) / zoom)
    );
    onseek(value);
  }

  function hoverMove(event: PointerEvent) {
    if (!jobId) return;
    const element = event.currentTarget as HTMLElement | null;
    if (!element) return;
    const rect = element.getBoundingClientRect();
    const time = Math.max(
      0,
      Math.min(sourceDuration, (event.clientX - rect.left - HEADER) / zoom)
    );
    hover = { x: event.clientX - rect.left, time };
    clearTimeout(hoverTimer);
    hoverTimer = setTimeout(() => {
      hoverFrame = jobFrameUrl(jobId, time);
    }, 120);
  }

  function hoverLeave() {
    hover = null;
    clearTimeout(hoverTimer);
  }

  function zoomFromWheel(event: WheelEvent) {
    event.preventDefault();
    const horizontal = event.shiftKey || Math.abs(event.deltaX) > Math.abs(event.deltaY);
    if (horizontal && scroller) {
      scroller.scrollLeft += event.deltaX || event.deltaY;
      return;
    }
    const direction = event.deltaY > 0 ? -1 : 1;
    zoom = Math.max(2, Math.min(400, zoom * (direction > 0 ? 1.16 : 0.86)));
  }

  onDestroy(() => {
    clearTimeout(hoverTimer);
    window.removeEventListener("pointermove", moveTrim);
    window.removeEventListener("pointerup", finishTrim);
    window.removeEventListener("pointercancel", finishTrim);
  });
</script>

<div class="overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-950" data-testid="recut-canvas">
  <div class="flex flex-wrap items-center justify-between gap-2 border-b border-neutral-800 px-3 py-2">
    <div class="flex flex-wrap items-center gap-2 text-[10px] text-neutral-400">
      <span class="flex items-center gap-1"><span class="h-2 w-3 rounded-sm border border-sky-400 bg-sky-500/30"></span>active</span>
      <span class="flex items-center gap-1"><span class="h-2 w-3 rounded-sm border border-rose-400 bg-rose-500/30"></span>inactive</span>
      <span class="text-neutral-600">{inactive.length} inactive segment(s)</span>
    </div>
    <span class="font-mono text-[10px] text-neutral-500">{Math.round(zoom)} px/s</span>
  </div>

  <div class="relative">
    <div bind:this={scroller} class="overflow-x-auto" data-testid="recut-scroller">
    <!-- svelte-ignore a11y_no_noninteractive_tabindex -->
    <!-- svelte-ignore a11y_no_noninteractive_element_interactions -->
    <div
      class="relative h-[190px] min-w-full"
      style={`width:${width}px`}
      role="application"
      aria-label="Recut source timeline"
      tabindex="0"
      onclick={seekFromEvent}
      onwheel={zoomFromWheel}
      onpointermove={hoverMove}
      onpointerleave={hoverLeave}
      onkeydown={(event) => {
        if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
        event.preventDefault();
        onseek?.(
          Math.max(
            0,
            Math.min(
              sourceDuration,
              playhead + (event.key === "ArrowRight" ? 1 : -1)
            )
          )
        );
      }}
    >
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
            onclick={() => selectBlock("inactive", item.id)}
            ondblclick={() => ontoggle(item.id, true)}
            disabled={busy}
            title={`Inactive (${reasonLabel(item.reason)}). Double-click to activate; drag an edge to move the cut.`}
            class={`absolute top-7 h-8 overflow-hidden rounded border px-1 text-left text-[9px] ${selectedId === item.id ? "border-rose-200 bg-rose-500/40 text-white ring-1 ring-rose-200" : "border-rose-400/70 bg-rose-500/20 text-rose-100 hover:bg-rose-500/30"}`}
            style={`left:${leftFor(displayStart(item))}px;width:${widthFor(displayStart(item), displayEnd(item))}px`}
          >
            <span
              role="separator"
              aria-label={`Trim ${item.id} start`}
              data-testid={`recut-trim-start-${item.id}`}
              class="absolute inset-y-0 left-0 z-10 w-2 cursor-ew-resize rounded-l bg-rose-200/40 hover:bg-rose-100/70"
              onpointerdown={(event) => beginTrim(event, item, "start")}
            ></span>
            <span
              role="separator"
              aria-label={`Trim ${item.id} end`}
              data-testid={`recut-trim-end-${item.id}`}
              class="absolute inset-y-0 right-0 z-10 w-2 cursor-ew-resize rounded-r bg-rose-200/40 hover:bg-rose-100/70"
              onpointerdown={(event) => beginTrim(event, item, "end")}
            ></span>
            <span class="pointer-events-none relative z-0 px-1">{item.id} · {reasonLabel(item.reason)}</span>
          </button>
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
          >
            {#if (waveforms[clip.id]?.length ?? 0) > 1}
              <svg class="pointer-events-none absolute inset-0 h-full w-full opacity-70" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
                <polygon points={wavePoints(waveforms[clip.id])} fill="#34d399" fill-opacity="0.45" stroke="#6ee7b7" stroke-width="0.6" />
              </svg>
            {/if}
            <span class="relative">{clip.id}</span>
          </button>
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

      {#if hover && hoverFrame}
        <div
          class="pointer-events-none absolute top-7 z-30 overflow-hidden rounded-lg border border-sky-400/40 bg-black shadow-2xl shadow-black/60"
          style={`left:${Math.max(HEADER + 8, Math.min(width - 174, hover.x + 12))}px`}
          data-testid="recut-hover-frame"
        >
          <img src={hoverFrame} alt="" class="h-[90px] w-[160px] object-cover" />
          <span class="absolute bottom-1 right-1 rounded bg-black/70 px-1 font-mono text-[9px] text-white">{hover.time.toFixed(2)}s</span>
        </div>
      {/if}
      {#if playhead > 0}
        <span class="absolute bottom-0 top-6 z-20 w-px bg-rose-300" style={`left:${leftFor(playhead)}px`} data-testid="recut-playhead"></span>
      {/if}
      <p class="absolute bottom-2 left-[96px] text-[9px] text-neutral-600">
        Source time · {sourceDuration.toFixed(1)}s · double-click a block to toggle it
      </p>
    </div>
    </div>
    <div class="absolute left-0 top-0 z-20 h-full w-[88px] border-r border-neutral-800 bg-neutral-950/95" data-testid="recut-track-headers">
      <p class="absolute left-2 top-1 text-[8px] font-bold text-neutral-500">RECUT</p>
      <span class="absolute left-2 top-[30px] text-[8px] font-bold text-neutral-400">V1 · VIDEO</span>
      {#if onToggleTrack}
        <div class="absolute left-1.5 top-[44px] flex items-center gap-0.5">
          <button type="button" onclick={() => onToggleTrack("video", "muted")} class={`rounded px-1 text-[8px] ${(tracks.video ?? { muted: false, solo: false, locked: false }).muted ? "bg-amber-500/25 text-amber-200" : "text-neutral-500 hover:text-neutral-200"}`} aria-label="Hide V1 · VIDEO">V</button>
          <button type="button" onclick={() => onToggleTrack("video", "solo")} class={`rounded px-1 text-[8px] ${(tracks.video ?? { muted: false, solo: false, locked: false }).solo ? "bg-amber-500/25 text-amber-200" : "text-neutral-500 hover:text-neutral-200"}`} aria-label="Solo V1 · VIDEO">S</button>
          <button type="button" onclick={() => onToggleTrack("video", "locked")} class={`rounded px-1 text-[8px] ${(tracks.video ?? { muted: false, solo: false, locked: false }).locked ? "bg-sky-500/25 text-sky-200" : "text-neutral-500 hover:text-neutral-200"}`} aria-label="Lock V1 · VIDEO">L</button>
        </div>
      {/if}
      <span class="absolute left-2 top-[100px] text-[8px] font-bold text-neutral-400">A1 · DIALOGUE</span>
      {#if onToggleTrack}
        <div class="absolute left-1.5 top-[114px] flex items-center gap-0.5">
          <button type="button" onclick={() => onToggleTrack("audio", "muted")} class={`rounded px-1 text-[8px] ${(tracks.audio ?? { muted: false, solo: false, locked: false }).muted ? "bg-rose-500/25 text-rose-200" : "text-neutral-500 hover:text-neutral-200"}`} aria-label="Mute A1 · DIALOGUE">M</button>
          <button type="button" onclick={() => onToggleTrack("audio", "solo")} class={`rounded px-1 text-[8px] ${(tracks.audio ?? { muted: false, solo: false, locked: false }).solo ? "bg-amber-500/25 text-amber-200" : "text-neutral-500 hover:text-neutral-200"}`} aria-label="Solo A1 · DIALOGUE">S</button>
          <button type="button" onclick={() => onToggleTrack("audio", "locked")} class={`rounded px-1 text-[8px] ${(tracks.audio ?? { muted: false, solo: false, locked: false }).locked ? "bg-sky-500/25 text-sky-200" : "text-neutral-500 hover:text-neutral-200"}`} aria-label="Lock A1 · DIALOGUE">L</button>
        </div>
      {/if}
    </div>
  </div>
</div>
