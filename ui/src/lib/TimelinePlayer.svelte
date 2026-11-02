<script lang="ts">
  import { onDestroy } from "svelte";
  import {
    jobOverlayFileUrl,
    jobSourceFileUrl,
    type TimelineData
  } from "$lib/api";
  import { liveOutputDuration, liveSegments, type LiveSegment } from "$lib/timelineView";

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
  const outputDuration = $derived(liveOutputDuration(segments));

  let videoA = $state<HTMLVideoElement | null>(null);
  let videoB = $state<HTMLVideoElement | null>(null);
  let audioA = $state<HTMLAudioElement | null>(null);
  let audioB = $state<HTMLAudioElement | null>(null);
  let frontIsB = $state(false);
  let index = $state(0);
  let playing = $state(false);
  let sourceTime = $state(0);
  let outputTime = $state(0);
  let error = $state("");
  let raf = 0;
  let lastReport = 0;
  let crossfading = $state(false);
  let transitionIndex = -1;
  let transitionDuration = 0;
  let transitionAudio = false;
  let frontOpacity = $state(1);
  let backOpacity = $state(0);
  let blackOpacity = $state(0);
  let blackFade: { start: number; duration: number } | null = null;

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
  const audioMuted = $derived(
    Boolean(timeline.tracks?.audio?.muted && !timeline.tracks?.audio?.solo)
  );
  const videoMuted = $derived(
    Boolean(timeline.tracks?.video?.muted && !timeline.tracks?.video?.solo)
  );
  const overlays = $derived(
    (timeline.overlays ?? []).filter((overlay) => {
      const start = overlay.start_frame / Math.max(1, timeline.fps);
      const end = (overlay.start_frame + overlay.duration_frames) / Math.max(1, timeline.fps);
      return outputTime >= start && outputTime < end;
    })
  );
  const titleCues = $derived(
    (timeline.titles ?? []).filter(
      (cue) => outputTime >= cue.start_sec && outputTime < cue.end_sec
    )
  );

  function frontVideo(): HTMLVideoElement | null {
    return frontIsB ? videoB : videoA;
  }
  function backVideo(): HTMLVideoElement | null {
    return frontIsB ? videoA : videoB;
  }
  function frontAudio(): HTMLAudioElement | null {
    return frontIsB ? audioB : audioA;
  }
  function backAudio(): HTMLAudioElement | null {
    return frontIsB ? audioA : audioB;
  }
  function gain(): number {
    return audioMuted ? 0 : 1;
  }

  function syncAudio(
    element: HTMLAudioElement | null,
    sourcePosition: number,
    segment: LiveSegment | undefined
  ) {
    if (!element || !segment) return;
    const range = audioRanges.get(segment.id);
    if (!range) return;
    const expected = range.start + Math.max(0, sourcePosition - segment.start);
    if (Math.abs(element.currentTime - expected) > 0.25) {
      element.currentTime = Math.min(range.end, Math.max(range.start, expected));
    }
  }

  function seekAudio(
    element: HTMLAudioElement | null,
    sourcePosition: number,
    segment: LiveSegment | undefined
  ) {
    if (!element || !segment) return;
    const range = audioRanges.get(segment.id);
    if (!range) return;
    const expected = range.start + Math.max(0, sourcePosition - segment.start);
    element.currentTime = Math.min(range.end, Math.max(range.start, expected));
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

  function beginCrossfade(nextIndex: number) {
    const next = segments[nextIndex];
    const back = backVideo();
    if (!current || !next || !back) return;
    const transition = current.transitionOut;
    if (!transition || transition.type !== "crossfade") return;
    crossfading = true;
    transitionIndex = nextIndex;
    transitionDuration = Math.max(0.01, transition.duration);
    transitionAudio = transition.audio;
    frontOpacity = 1;
    backOpacity = 0;
    const outgoing = frontVideo();
    const remaining = outgoing ? current.end - outgoing.currentTime : 0;
    const elapsed = Math.max(
      0,
      Math.min(transition.duration, transition.duration - Math.max(0, remaining))
    );
    back.currentTime = Math.min(next.end, next.start + elapsed);
    void back.play().catch(() => undefined);
    const incomingAudio = backAudio();
    if (incomingAudio) {
      seekAudio(incomingAudio, back.currentTime, next);
      incomingAudio.volume = 0;
      void incomingAudio.play().catch(() => undefined);
    }
  }

  function crossfadeAudio(progress: number) {
    const level = gain();
    const outgoing = frontAudio();
    const incoming = backAudio();
    if (outgoing) outgoing.volume = transitionAudio ? (1 - progress) * level : level;
    if (incoming) incoming.volume = transitionAudio ? progress * level : 0;
  }

  function finishCrossfade() {
    const next = segments[transitionIndex];
    const outgoingVideo = frontVideo();
    const outgoingAudio = frontAudio();
    const incomingVideo = backVideo();
    const incomingAudio = backAudio();
    outgoingVideo?.pause();
    outgoingAudio?.pause();
    frontIsB = !frontIsB;
    index = Math.min(transitionIndex, Math.max(0, segments.length - 1));
    crossfading = false;
    transitionIndex = -1;
    frontOpacity = 1;
    backOpacity = 0;
    blackOpacity = 0;
    if (incomingVideo) {
      incomingVideo.volume = 1;
      void incomingVideo.play().catch(() => undefined);
    }
    if (incomingAudio) {
      incomingAudio.volume = gain();
      void incomingAudio.play().catch(() => undefined);
    }
    sourceTime = incomingVideo?.currentTime ?? next?.start ?? sourceTime;
    outputTime = next
      ? next.outputStart + Math.max(0, sourceTime - next.start)
      : outputTime;
    report();
    stopLoop();
    raf = requestAnimationFrame(tick);
  }

  function finishPlayback() {
    playing = false;
    stopLoop();
    frontVideo()?.pause();
    backVideo()?.pause();
    frontAudio()?.pause();
    backAudio()?.pause();
    blackOpacity = 0;
    blackFade = null;
    sourceTime = current?.end ?? sourceTime;
    outputTime = outputDuration;
    report();
  }

  function advance() {
    if (index + 1 >= segments.length) {
      finishPlayback();
      return;
    }
    const next = segments[index + 1];
    const video = frontVideo();
    const audio = frontAudio();
    const fade = current?.transitionOut;
    blackFade =
      fade && fade.type === "fade_to_black"
        ? { start: next.outputStart, duration: fade.duration }
        : null;
    blackOpacity = fade && fade.type === "fade_to_black" ? 1 : 0;
    index = Math.min(index + 1, Math.max(0, segments.length - 1));
    if (video) video.currentTime = next.start;
    seekAudio(audio, next.start, next);
    if (playing) {
      void video?.play().catch(() => undefined);
      void audio?.play().catch(() => undefined);
    }
    sourceTime = next.start;
    outputTime = next.outputStart;
    report();
    stopLoop();
    raf = requestAnimationFrame(tick);
  }

  function tick() {
    const video = frontVideo();
    if (!video || !playing || !current) return;
    const time = video.currentTime;
    const remaining = current.end - time;
    if (crossfading) {
      const progress = Math.max(
        0,
        Math.min(1, 1 - Math.max(0, remaining) / Math.max(0.01, transitionDuration))
      );
      frontOpacity = 1 - progress;
      backOpacity = progress;
      crossfadeAudio(progress);
      if (remaining <= 0.02) {
        finishCrossfade();
        return;
      }
    } else {
      frontOpacity = 1;
      backOpacity = 0;
      const outgoing = frontAudio();
      if (outgoing) outgoing.volume = gain();
      const incoming = backAudio();
      if (incoming) incoming.volume = 0;
      if (blackFade) {
        const progress = Math.max(
          0,
          Math.min(1, (outputTime - blackFade.start) / Math.max(0.01, blackFade.duration))
        );
        blackOpacity = 1 - progress;
        if (progress >= 1) blackFade = null;
      } else if (
        current.transitionOut?.type === "fade_to_black" &&
        remaining <= current.transitionOut.duration
      ) {
        blackOpacity = Math.max(
          0,
          Math.min(1, 1 - remaining / Math.max(0.01, current.transitionOut.duration))
        );
      }
      if (
        current.transitionOut?.type === "crossfade" &&
        remaining <= current.transitionOut.duration &&
        remaining > 0.02 &&
        index + 1 < segments.length
      ) {
        beginCrossfade(index + 1);
      }
      if (remaining <= 0.02) {
        advance();
        return;
      }
    }
    sourceTime = time;
    outputTime = current.outputStart + Math.max(0, time - current.start);
    syncAudio(frontAudio(), time, current);
    if (crossfading) {
      const next = segments[transitionIndex];
      const incoming = backVideo();
      if (incoming && next) syncAudio(backAudio(), incoming.currentTime, next);
    }
    report();
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
    crossfading = false;
    transitionIndex = -1;
    frontIsB = false;
    frontOpacity = 1;
    backOpacity = 0;
    blackOpacity = 0;
    blackFade = null;
    index = target.index;
    sourceTime = target.time;
    const segment = segments[index];
    outputTime = segment
      ? segment.outputStart + Math.max(0, target.time - segment.start)
      : 0;
    const video = videoA;
    if (video) video.currentTime = target.time;
    const audio = audioA;
    if (audio) {
      seekAudio(audio, target.time, segment);
      audio.volume = gain();
    }
    videoB?.pause();
    audioB?.pause();
    report();
    if (playing) {
      stopLoop();
      void video?.play().catch(() => undefined);
      void audio?.play().catch(() => undefined);
      raf = requestAnimationFrame(tick);
    }
  }

  function togglePlay() {
    const video = frontVideo();
    if (!video || !segments.length) return;
    error = "";
    if (playing) {
      video.pause();
      backVideo()?.pause();
      frontAudio()?.pause();
      backAudio()?.pause();
      playing = false;
      stopLoop();
      return;
    }
    if (outputTime >= outputDuration - 0.01) {
      seek(segments[0].start);
    }
    if (video.currentTime < current.start || video.currentTime >= current.end) {
      video.currentTime = current.start;
    }
    seekAudio(frontAudio(), video.currentTime, current);
    if (frontAudio()) frontAudio()!.volume = gain();
    const audio = frontAudio();
    const playback: Array<Promise<unknown>> = [
      video.play(),
      audio ? audio.play() : Promise.resolve()
    ];
    if (crossfading) {
      const incomingVideo = backVideo();
      const incomingAudio = backAudio();
      if (incomingVideo) playback.push(incomingVideo.play());
      if (incomingAudio) playback.push(incomingAudio.play());
    }
    void Promise.all(playback)
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
    const nextIndex = Math.min(segments.length - 1, index + 1);
    seek(segments[nextIndex].start);
  }

  $effect(() => {
    const job = jobId;
    const count = segments.length;
    if (!job || count === 0) return;
    index = 0;
    playing = false;
    crossfading = false;
    transitionIndex = -1;
    frontIsB = false;
    frontOpacity = 1;
    backOpacity = 0;
    blackOpacity = 0;
    blackFade = null;
    stopLoop();
    sourceTime = segments[0].start;
    outputTime = 0;
    error = "";
    [videoA, videoB, audioA, audioB].forEach((element) => element?.pause());
    if (videoA) videoA.currentTime = sourceTime;
    if (audioA) {
      seekAudio(audioA, sourceTime, segments[0]);
      audioA.volume = gain();
    }
  });

  onDestroy(() => {
    stopLoop();
    playing = false;
    [videoA, videoB, audioA, audioB].forEach((element) => element?.pause());
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

  <audio bind:this={audioA} src={sourceUrl} preload="auto"></audio>
  <audio bind:this={audioB} src={sourceUrl} preload="auto"></audio>

  <div class="relative overflow-hidden rounded-xl border border-neutral-800 bg-black" data-testid="live-composite">
    <video
      bind:this={videoA}
      src={sourceUrl}
      preload="auto"
      muted
      playsinline
      class="block max-h-[360px] w-full"
      style={`opacity:${frontIsB ? backOpacity : frontOpacity}`}
      onerror={() => (error = "The source media could not be loaded for live playback.")}
    >
      <track kind="captions" src="data:text/vtt;charset=utf-8,WEBVTT%0A%0A" />
    </video>
    <video
      bind:this={videoB}
      src={sourceUrl}
      preload="auto"
      muted
      playsinline
      class="absolute inset-0 h-full w-full"
      style={`opacity:${frontIsB ? frontOpacity : backOpacity}`}
      onerror={() => (error = "The source media could not be loaded for live playback.")}
    >
      <track kind="captions" src="data:text/vtt;charset=utf-8,WEBVTT%0A%0A" />
    </video>

    {#if videoMuted}
      <div class="absolute inset-0 bg-black" data-testid="live-video-muted"></div>
    {/if}

    <div class="pointer-events-none absolute inset-0" data-testid="live-overlays">
      {#each overlays as overlay (overlay.overlay_id)}
        {#if overlay.kind === "image"}
          <img
            src={jobOverlayFileUrl(jobId, overlay.overlay_id)}
            alt=""
            class="absolute object-contain"
            style={`left:${overlay.position_x * 100}%;top:${overlay.position_y * 100}%;width:${overlay.width_ratio * 100}%;opacity:${overlay.opacity};transform:translate(-50%,-50%)`}
          />
        {:else}
          <video
            src={jobOverlayFileUrl(jobId, overlay.overlay_id)}
            autoplay
            muted
            loop
            playsinline
            class="absolute object-contain"
            style={`left:${overlay.position_x * 100}%;top:${overlay.position_y * 100}%;width:${overlay.width_ratio * 100}%;opacity:${overlay.opacity};transform:translate(-50%,-50%)`}
          >
            <track kind="captions" src="data:text/vtt;charset=utf-8,WEBVTT%0A%0A" />
          </video>
        {/if}
      {/each}
    </div>

    <div class="pointer-events-none absolute inset-0" data-testid="live-titles">
      {#each titleCues as cue, cueIndex (cueIndex)}
        {#if cue.style === "title"}
          <p class="absolute inset-x-0 top-[42%] text-center text-2xl font-bold text-white drop-shadow-[0_2px_8px_rgba(0,0,0,0.9)]">{cue.text}</p>
        {:else}
          <p class="absolute bottom-[8%] left-[6%] rounded bg-black/55 px-3 py-1 text-sm font-semibold text-white">{cue.text}</p>
        {/if}
      {/each}
    </div>

    <div class="pointer-events-none absolute inset-0 bg-black" style={`opacity:${blackOpacity}`} data-testid="live-fade"></div>
  </div>

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
