<script lang="ts">
  import { onMount } from "svelte";
  import {
    errorMessage,
    getTimeline,
    jobArtifactUrl,
    listJobs,
    type Job,
    type TimelineData
  } from "$lib/api";

  let jobs = $state<Job[]>([]);
  let selected = $state("");
  let timeline = $state<TimelineData | null>(null);
  let loading = $state(false);
  let error = $state("");
  let playhead = $state(0);

  const duration = $derived(Math.max(1, timeline?.duration_sec ?? 1));
  const previewJob = $derived(jobs.find((job) => job.job_id === selected));
  const previewArtifact = $derived(
    Object.entries(previewJob?.result?.artifacts ?? {}).find(([name]) =>
      name === "mp4" || name.endsWith("mp4")
    )?.[0] ?? ""
  );

  const ticks = $derived(
    Array.from({ length: 11 }, (_, index) => ({
      at: (duration * index) / 10,
      left: index * 10
    }))
  );

  onMount(() => void loadJobs());

  async function loadJobs() {
    try {
      jobs = (await listJobs()).filter((job) => job.status === "succeeded");
      if (jobs[0]) {
        selected = jobs[0].job_id;
        await loadTimeline();
      }
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function loadTimeline() {
    if (!selected) return;
    loading = true;
    error = "";
    try {
      timeline = await getTimeline(selected);
      playhead = 0;
    } catch (reason) {
      error = errorMessage(reason);
      timeline = null;
    } finally {
      loading = false;
    }
  }

  function pct(value: number): number {
    return Math.max(0, Math.min(100, (value / duration) * 100));
  }
</script>

<div class="space-y-4">
  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold text-white">Timeline</h2>
        <p class="mt-1 text-xs text-neutral-500">Read-only storyboard from the latest successful recipe job.</p>
      </div>
      <div class="flex items-center gap-2">
        <select bind:value={selected} onchange={() => void loadTimeline()} class="max-w-[280px] rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-200">
          {#each jobs as job}
            <option value={job.job_id}>{job.result?.recipe_id ?? "recipe"} · {job.job_id.slice(0, 8)}</option>
          {/each}
        </select>
        <button type="button" onclick={() => void loadTimeline()} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 hover:border-sky-500">Refresh</button>
      </div>
    </div>
    {#if loading}<p class="mt-2 text-[11px] text-neutral-500">Loading timeline…</p>{/if}
    {#if error}<p class="mt-2 text-[11px] text-rose-300">{error}</p>{/if}
    {#if !loading && !jobs.length}<p class="mt-2 text-[11px] text-neutral-500">Run a recipe to populate the timeline.</p>{/if}
  </section>

  {#if timeline}
    <section class="overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-950">
      <div class="border-b border-neutral-800 p-3">
        <div class="relative h-6">
          {#each ticks as tick}
            <span class="absolute top-0 text-[9px] text-neutral-600" style={`left: ${tick.left}%`}>{tick.at.toFixed(1)}s</span>
          {/each}
        </div>
        <input type="range" min="0" max={duration} step="0.01" bind:value={playhead} class="w-full accent-sky-400" />
      </div>
      <div class="space-y-2 p-3">
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <span class="text-[10px] uppercase tracking-wide text-neutral-500">Video</span>
          <div class="relative h-14 rounded-lg bg-neutral-900">
            {#each timeline.video as clip}
              <button type="button" class="absolute top-1 h-12 overflow-hidden rounded border border-sky-500/40 bg-sky-500/20 px-1 text-left text-[9px] text-sky-200" style={`left:${pct(clip.start_sec)}%;width:${Math.max(0.5, pct(clip.end_sec) - pct(clip.start_sec))}%`} title={clip.id}>
                <span class="block truncate">{clip.id}</span>
                {#if clip.keyframes}<span class="text-[8px] text-sky-300/70">zoom {clip.keyframes} keys</span>{/if}
                {#if clip.transition}<span class="text-[8px] text-amber-300/80">{clip.transition}</span>{/if}
              </button>
            {/each}
            <div class="pointer-events-none absolute bottom-0 top-0 w-px bg-rose-400" style={`left:${pct(playhead)}%`}></div>
          </div>
        </div>
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <span class="text-[10px] uppercase tracking-wide text-neutral-500">Audio</span>
          <div class="relative h-10 rounded-lg bg-neutral-900">
            {#each timeline.audio as clip}
              <div class="absolute top-1 h-8 rounded bg-emerald-500/20" style={`left:${pct(clip.start_sec)}%;width:${Math.max(0.5, pct(clip.end_sec) - pct(clip.start_sec))}%`} title={clip.id}></div>
            {/each}
          </div>
        </div>
        <div class="grid grid-cols-[90px_1fr] items-center gap-3">
          <span class="text-[10px] uppercase tracking-wide text-neutral-500">Captions</span>
          <div class="relative h-14 rounded-lg bg-neutral-900">
            {#each timeline.captions as caption}
              <div class="absolute top-1 h-12 overflow-hidden rounded border border-violet-500/30 bg-violet-500/15 px-1 text-[8px] text-violet-200" style={`left:${pct(caption.start_sec)}%;width:${Math.max(0.5, pct(caption.end_sec) - pct(caption.start_sec))}%`} title={caption.text}>
                <span class="line-clamp-3">{caption.text}</span>
              </div>
            {/each}
          </div>
        </div>
        {#if Object.keys(timeline.broll ?? {}).length}
          <div class="grid grid-cols-[90px_1fr] items-center gap-3">
            <span class="text-[10px] uppercase tracking-wide text-neutral-500">B-roll</span>
            <div class="relative h-10 rounded-lg bg-neutral-900">
              <span class="absolute left-2 top-2 text-[9px] text-amber-300">{Object.keys(timeline.broll).length} planned Short(s)</span>
            </div>
          </div>
        {/if}
      </div>
      {#if previewArtifact}
        <div class="border-t border-neutral-800 p-3">
          <video class="max-h-[420px] w-full rounded-lg bg-black" controls preload="metadata" src={jobArtifactUrl(selected, previewArtifact)}><track kind="captions" src="data:text/vtt;charset=utf-8,WEBVTT%0A%0A" /></video>
        </div>
      {/if}
    </section>
  {/if}
</div>
