<script lang="ts">
  import { onDestroy } from "svelte";
  import { jobSourceFileUrl, type TimelineData } from "$lib/api";
  import { liveSegments } from "$lib/timelineView";

  let {
    jobId,
    timeline,
    ontime
  }: {
    jobId: string;
    timeline: TimelineData;
    ontime?: (sourceSec: number, outputSec: number) => void;
  } = $props();

  const segments = $derived(liveSegments(timeline.video, timeline.fps));

  const sourceDuration = $derived(
    Math.max(
      timeline.source_duration_sec || 0,
      ...segments.map((segment) => segment.end),
      1
    )
  );
  const outputDuration = $derived(
    segments.reduce((total, segment) => total + (segment.end - segment.start), 0)
  );

  let videoEl = $state<HTMLVideoElement | null>(null);
  let audioEl = $state<HTMLAudioElement | null>(null);
  let index = $state(0);
  let playing = $state(false);
  let sourceTime = $state(0);
  let outputTime = $state(0);
  let error = $state("");
  let raf = 0;
  let lastReport = 0;

  const sourceUrl = $derived(jobSourceFileUrl(jobId));
  const audioRanges = $derived(
    new Map(
      timeline.audio.map((clip) => [
        clip.id,
        {
          start: clip.source_in_sec ?? clip.start_sec,
          end: clip.source_out_sec ?? clip.end_sec
        }
      ])
    )
  );
  const current = $derived(segments[Math.min(index, Math.max(0, segments.length - 1))]);
  const currentAudio = $derived(current ? audioRanges.get(current.id) : null);

  function syncAudio(sourcePosition: number, segment: typeof current) {
    if (!audioEl || !segment) return;
    const range = audioRanges.get(segment.id);
    if (!range) return;
    const expected = range.start + Math.max(0, sourcePosition - segment.start);
    if (Math.abs(audioEl.currentTime - expected) > 0.25) {
      audioEl.currentTime = Math.min(range.end, Math.max(range.start, expected));
    }
  }

  function report() {
    if (performance.now() - lastReport < 80) return;
    lastReport = performance.now();
    ontime?.(sourceTime, outputTime);
  }

  function stopLoop() {
    cancelAnimationFrame(raf);
    raf = 0;
  }

  function tick() {
    if (!videoEl || !playing || !current) return;
    const time = videoEl.currentTime;
    if (time >= current.end - 0.02) {
      advance();
      return;
    }
    sourceTime = time;
    outputTime = current.outputStart + Math.max(0, time - current.start);
    syncAudio(time, current);
    report();
    raf = requestAnimationFrame(tick);
  }

  function advance() {
    if (!videoEl) return;
    if (index + 1 >= segments.length) {
      playing = false;
      stopLoop();
      audioEl?.pause();
      sourceTime = current?.end ?? sourceTime;
      outputTime = outputDuration;
      report();
      return;
    }
    index += 1;
    const next = segments[index];
    const nextAudio = audioRanges.get(next.id);
    videoEl.currentTime = next.start;
    if (audioEl && nextAudio) audioEl.currentTime = nextAudio.start;
    if (playing) {
      void videoEl.play().catch(() => undefined);
      void audioEl?.play().catch(() => undefined);
    }
    sourceTime = next.start;
    outputTime = next.outputStart;
    report();
    stopLoop();
    raf = requestAnimationFrame(tick);
  }

  function seekTarget(time: number): { index: number; time: number } {
    if (!segments.length) return { index: 0, time: 0 };
    const target = Math.max(0, Math.min(sourceDuration, time));
    for (let position = 0; position < segments.length; position += 1) {
      const segment = segments[position];
      if (target < segment.start) return { index: position, time: segment.start };
      if (target <= segment.end) return { index: position, time: target };
    }
    const last = segments[segments.length - 1];
    return { index: segments.length - 1, time: last.end };
  }

  function seek(time: number) {
    const target = seekTarget(time);
    index = target.index;
    sourceTime = target.time;
    const segment = segments[index];
    outputTime = segment ? segment.outputStart + Math.max(0, target.time - segment.start) : 0;
    if (videoEl) videoEl.currentTime = target.time;
    if (audioEl && segment) {
      const range = audioRanges.get(segment.id);
      if (range) {
        audioEl.currentTime = Math.min(
          range.end,
          range.start + Math.max(0, target.time - segment.start)
        );
      }
    }
    report();
    if (playing) {
      stopLoop();
      raf = requestAnimationFrame(tick);
    }
  }

  function togglePlay() {
    if (!videoEl || !segments.length) return;
    error = "";
    if (playing) {
      videoEl.pause();
      audioEl?.pause();
      playing = false;
      stopLoop();
      return;
    }
    if (outputTime >= outputDuration - 0.01) {
      index = 0;
      sourceTime = segments[0].start;
      outputTime = 0;
    }
    if (videoEl.currentTime < current.start || videoEl.currentTime >= current.end) {
      videoEl.currentTime = current.start;
    }
    if (audioEl && currentAudio) {
      const expected =
        currentAudio.start + Math.max(0, videoEl.currentTime - current.start);
      audioEl.currentTime = Math.min(
        currentAudio.end,
        Math.max(currentAudio.start, expected)
      );
    }
    void Promise.all([
      videoEl.play(),
      audioEl ? audioEl.play() : Promise.resolve()
    ])
      .then(() => {
        playing = true;
        stopLoop();
        raf = requestAnimationFrame(tick);
      })
      .catch((reason: unknown) => {
        error = reason instanceof Error ? reason.message : "Playback was blocked.";
      });
  }

  function nextSegment() {
    if (!segments.length) return;
    index = Math.min(segments.length - 1, index + 1);
    const segment = segments[index];
    sourceTime = segment.start;
    outputTime = segment.outputStart;
    if (videoEl) videoEl.currentTime = segment.start;
    const audioRange = audioRanges.get(segment.id);
    if (audioEl && audioRange) audioEl.currentTime = audioRange.start;
    report();
  }

  $effect(() => {
    const job = jobId;
    const count = segments.length;
    if (!job || count === 0) return;
    index = 0;
    playing = false;
    stopLoop();
    sourceTime = segments[0].start;
    outputTime = 0;
    error = "";
    if (videoEl) videoEl.currentTime = sourceTime;
    const firstAudio = audioRanges.get(segments[0].id);
    if (audioEl && firstAudio) audioEl.currentTime = firstAudio.start;
  });

  onDestroy(() => {
    stopLoop();
    playing = false;
  });
</script>

<div class="mb-2 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-3" data-testid="live-player">
  <div class="mb-2 flex flex-wrap items-center justify-between gap-2">
    <div class="flex items-center gap-2">
      <span class="rounded-full border border-emerald-400/30 bg-emerald-500/10 px-2 py-0.5 text-[9px] uppercase tracking-wide text-emerald-200">live recut</span>
      <p class="text-[10px] text-neutral-500">
        {index + 1}/{segments.length} active · skips {timeline.inactive.length} inactive
      </p>
    </div>
    <div class="flex items-center gap-1.5">
      <span class="font-mono text-[10px] text-neutral-400">{outputTime.toFixed(2)}s / {outputDuration.toFixed(2)}s</span>
      <button type="button" onclick={nextSegment} disabled={index + 1 >= segments.length} class="rounded-lg border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 disabled:opacity-40">Next active</button>
      <button type="button" onclick={togglePlay} disabled={!segments.length} class="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1 text-[11px] text-sky-200 disabled:opacity-40">
        {playing ? "Pause" : "Play"}
      </button>
    </div>
  </div>

  <audio bind:this={audioEl} src={sourceUrl} preload="auto"></audio>
  <video
    bind:this={videoEl}
    src={sourceUrl}
    preload="auto"
    muted
    playsinline
    class="max-h-[360px] w-full rounded-xl border border-neutral-800 bg-black"
    onerror={() => (error = "The source media could not be loaded for live playback.")}
    onplay={() => {
      playing = true;
      stopLoop();
      raf = requestAnimationFrame(tick);
    }}
    onpause={() => {
      playing = false;
      audioEl?.pause();
      stopLoop();
    }}
    onended={advance}
  >
    <track kind="captions" src="data:text/vtt;charset=utf-8,WEBVTT%0A%0A" />
  </video>

  <label class="mt-2 block">
    <span class="sr-only">Source position</span>
    <input
      type="range"
      min="0"
      max={sourceDuration}
      step="0.01"
      value={sourceTime}
      oninput={(event) => seek(Number(event.currentTarget.value))}
      class="w-full accent-sky-400"
    />
  </label>
  <div class="mt-1 flex justify-between font-mono text-[9px] text-neutral-600">
    <span>source {sourceTime.toFixed(2)}s</span>
    <span>output {outputTime.toFixed(2)}s</span>
  </div>
  {#if error}<p class="mt-1 text-[10px] text-rose-300">{error}</p>{/if}
</div>
