<script lang="ts">
  import { onMount } from "svelte";
  import {
    errorMessage,
    getTimeline,
    jobArtifactUrl,
    editTimeline,
    listJobs,
    updateJobCaption,
    type Job,
    type TimelineData
  } from "$lib/api";

  let jobs = $state<Job[]>([]);
  let selected = $state("");
  let timeline = $state<TimelineData | null>(null);
  let loading = $state(false);
  let error = $state("");
  let playhead = $state(0);
  let selectedCaption = $state<number | null>(null);
  let captionDraft = $state("");
  let captionBusy = $state(false);
  let captionStatus = $state("");
  let selectedClip = $state<TimelineData["video"][number] | null>(null);
  let clipStart = $state(0);
  let clipEnd = $state(0);
  let clipDelta = $state(0);
  let editBusy = $state(false);
  let editStatus = $state("");

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

  function selectClip(clip: TimelineData["video"][number]) {
    selectedClip = clip;
    clipStart = clip.start_sec;
    clipEnd = clip.end_sec;
    clipDelta = 1;
    editStatus = "";
  }

  async function applyEdit(action: "trim" | "move" | "delete") {
    if (!selectedClip) return;
    editBusy = true;
    editStatus = "";
    try {
      const response = await editTimeline(selected, {
        clip_id: selectedClip.id,
        action,
        start_sec: action === "trim" ? clipStart : undefined,
        end_sec: action === "trim" ? clipEnd : undefined,
        delta_sec: action === "move" ? clipDelta : undefined
      });
      editStatus = response.warning;
      selectedClip = null;
      await loadTimeline();
    } catch (reason) {
      editStatus = errorMessage(reason);
    } finally {
      editBusy = false;
    }
  }

  function editCaption(caption: TimelineData["captions"][number]) {
    selectedCaption = caption.id;
    captionDraft = caption.text;
    captionStatus = "";
  }

  async function saveCaption() {
    if (selectedCaption === null || !timeline) return;
    captionBusy = true;
    captionStatus = "";
    try {
      await updateJobCaption(selected, selectedCaption, captionDraft.trim());
      timeline = {
        ...timeline,
        captions: timeline.captions.map((caption) =>
          caption.id === selectedCaption ? { ...caption, text: captionDraft.trim() } : caption
        )
      };
      captionStatus = "Saved to project_state.json";
    } catch (reason) {
      captionStatus = errorMessage(reason);
    } finally {
      captionBusy = false;
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
              <button type="button" onclick={() => selectClip(clip)} class={`absolute top-1 h-12 overflow-hidden rounded border px-1 text-left text-[9px] ${selectedClip?.id === clip.id ? "border-sky-300 bg-sky-500/35 text-white" : "border-sky-500/40 bg-sky-500/20 text-sky-200"}`} style={`left:${pct(clip.start_sec)}%;width:${Math.max(0.5, pct(clip.end_sec) - pct(clip.start_sec))}%`} title={clip.id}>
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
              <button type="button" onclick={() => editCaption(caption)} class={`absolute top-1 h-12 overflow-hidden rounded border px-1 text-left text-[8px] ${selectedCaption === caption.id ? "border-sky-400 bg-sky-500/25 text-sky-100" : "border-violet-500/30 bg-violet-500/15 text-violet-200"}`} style={`left:${pct(caption.start_sec)}%;width:${Math.max(0.5, pct(caption.end_sec) - pct(caption.start_sec))}%`} title={caption.text}>
                <span class="line-clamp-3">{caption.text}</span>
              </button>
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
      {#if selectedClip}
        <div class="border-t border-neutral-800 p-3">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Edit clip {selectedClip.id}</p>
          <div class="mt-2 flex flex-wrap items-end gap-2">
            <label class="text-[10px] text-neutral-400">Start (s)<input type="number" min="0" step="0.01" bind:value={clipStart} class="mt-1 block w-24 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" /></label>
            <label class="text-[10px] text-neutral-400">End (s)<input type="number" min="0" step="0.01" bind:value={clipEnd} class="mt-1 block w-24 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" /></label>
            <button type="button" onclick={() => void applyEdit("trim")} disabled={editBusy} class="rounded border border-sky-500/40 px-2 py-1 text-[10px] text-sky-300 disabled:opacity-40">Trim</button>
            <label class="text-[10px] text-neutral-400">Move (s)<input type="number" step="0.1" bind:value={clipDelta} class="mt-1 block w-20 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" /></label>
            <button type="button" onclick={() => void applyEdit("move")} disabled={editBusy} class="rounded border border-neutral-600 px-2 py-1 text-[10px] text-neutral-300 disabled:opacity-40">Move</button>
            <button type="button" onclick={() => void applyEdit("delete")} disabled={editBusy} class="rounded border border-rose-500/40 px-2 py-1 text-[10px] text-rose-300 disabled:opacity-40">Delete</button>
          </div>
          {#if editStatus}<p class="mt-1 text-[10px] text-amber-300">{editStatus}</p>{/if}
        </div>
      {/if}
      {#if selectedCaption !== null}
        <div class="border-t border-neutral-800 p-3">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Edit caption #{selectedCaption}</p>
          <textarea rows="3" bind:value={captionDraft} class="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"></textarea>
          <div class="mt-2 flex items-center gap-2">
            <button type="button" onclick={() => void saveCaption()} disabled={captionBusy} class="rounded border border-sky-500/40 px-2 py-1 text-[10px] text-sky-300 disabled:opacity-40">{captionBusy ? "Saving…" : "Save caption"}</button>
            {#if captionStatus}<span class="text-[10px] text-neutral-400">{captionStatus}</span>{/if}
          </div>
        </div>
      {/if}
      {#if previewArtifact}
        <div class="border-t border-neutral-800 p-3">
          <video class="max-h-[420px] w-full rounded-lg bg-black" controls preload="metadata" src={jobArtifactUrl(selected, previewArtifact)}><track kind="captions" src="data:text/vtt;charset=utf-8,WEBVTT%0A%0A" /></video>
        </div>
      {/if}
    </section>
  {/if}
</div>
