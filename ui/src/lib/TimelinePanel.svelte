<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import TimelineCanvas from "$lib/TimelineCanvas.svelte";
  import ShortEditor from "$lib/ShortEditor.svelte";
  import WaveformStrip from "$lib/WaveformStrip.svelte";
  import {
    approveBroll,
    cancelPreview,
    createJobPreview,
    editTimeline,
    errorMessage,
    getJobReview,
    getJobThumbnails,
    getPreviewStatus,
    getTimeline,
    jobArtifactUrl,
    jobThumbnailUrl,
    listJobs,
    decideJobReview,
    selectJobThumbnail,
    redoTimeline,
    undoTimeline,
    updateJobCaption,
    updateTimelineClip,
    type Job,
    type TimelineData
  } from "$lib/api";

  let jobs = $state<Job[]>([]);
  let selected = $state("");
  let timeline = $state<TimelineData | null>(null);
  let loading = $state(false);
  let error = $state("");
  let status = $state("");
  let playhead = $state(0);
  let zoom = $state(80);
  let snap = $state(true);
  let selectedClip = $state<TimelineData["video"][number] | null>(null);
  let clipStart = $state(0);
  let clipEnd = $state(0);
  let clipDelta = $state(1);
  let editBusy = $state(false);
  let editStatus = $state("");
  let transitionType = $state<"crossfade" | "fade_to_black" | "none">("none");
  let transitionFrames = $state(6);
  let clipScale = $state(1);
  let posX = $state(0);
  let posY = $state(0);
  let fadeIn = $state(0);
  let fadeOut = $state(0);
  let styleBusy = $state(false);
  let reviewChecks = $state<Array<{ id: string; label: string; ok: boolean }>>([]);
  let reviewApproval = $state<Record<string, unknown>>({});
  let reviewComment = $state("");
  let reviewBusy = $state(false);
  let thumbnails = $state<{ variants: string[]; selected: string }>({ variants: [], selected: "" });
  let selectedCaption = $state<number | null>(null);
  let captionDraft = $state("");
  let captionBusy = $state(false);
  let captionStatus = $state("");
  let previewUrl = $state("");
  let previewBusy = $state(false);
  let previewPercent = $state(0);
  let previewMessage = $state("");
  let videoEl = $state<HTMLVideoElement | null>(null);
  let playing = $state(false);
  let brollOrder = $state<Record<string, number[]>>({});
  let brollApproved = $state<Record<string, number[]>>({});
  let brollBusy = $state("");
  let raf = 0;
  let shortEditor = $state<{ index: number; short: TimelineData["shorts"][number] } | null>(null);

  const duration = $derived(Math.max(0.001, timeline?.duration_sec ?? 1));
  const fps = $derived(timeline?.fps ?? 30);
  const previewJob = $derived(jobs.find((job) => job.job_id === selected));
  const previewArtifact = $derived(
    Object.entries(previewJob?.result?.artifacts ?? {}).find(
      ([name]) => name === "mp4" || name.endsWith("mp4")
    )?.[0] ?? ""
  );
  const canPreview = $derived(Boolean(previewUrl || previewArtifact));

  onMount(() => {
    void loadJobs();
    window.addEventListener("keydown", onKeydown);
  });

  onDestroy(() => {
    window.removeEventListener("keydown", onKeydown);
    cancelAnimationFrame(raf);
  });

  function timecode(value: number): string {
    const safe = Math.max(0, value);
    const minutes = Math.floor(safe / 60);
    const seconds = safe - minutes * 60;
    const frames = Math.floor((seconds - Math.floor(seconds)) * Math.max(1, fps));
    return `${String(minutes).padStart(2, "0")}:${seconds.toFixed(0).padStart(2, "0")}:${String(frames).padStart(2, "0")}`;
  }

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

  async function loadTimeline(keepClipId = "") {
    if (!selected) return;
    loading = true;
    error = "";
    editStatus = "";
    try {
      timeline = await getTimeline(selected);
      if (!keepClipId) playhead = 0;
      selectedCaption = null;
      const keep = keepClipId
        ? timeline.video.find((clip) => clip.id === keepClipId) ?? null
        : null;
      selectClip(keep);
      previewUrl = "";
      const artifacts = previewJob?.result?.artifacts ?? {};
      const mp4 = Object.entries(artifacts).find(([name]) => name === "mp4" || name.endsWith("mp4"));
      previewUrl = mp4 ? jobArtifactUrl(selected, mp4[0]) : "";
      syncBroll(timeline);
      await loadDeliverables();
    } catch (reason) {
      error = errorMessage(reason);
      timeline = null;
    } finally {
      loading = false;
    }
  }

  async function loadDeliverables() {
    try {
      const review = await getJobReview(selected);
      const payload = (review.review ?? {}) as {
        checks?: Array<{ id: string; label: string; ok: boolean }>;
      };
      reviewChecks = payload.checks ?? [];
      reviewApproval = review.approval ?? {};
    } catch {
      reviewChecks = [];
      reviewApproval = {};
    }
    try {
      thumbnails = await getJobThumbnails(selected);
    } catch {
      thumbnails = { variants: [], selected: "" };
    }
  }

  async function decideReview(approved: boolean) {
    reviewBusy = true;
    error = "";
    try {
      await decideJobReview(selected, {
        approved,
        comment: reviewComment,
        reviewer: "local operator"
      });
      status = approved ? "Review approved." : "Review rejected.";
      await loadDeliverables();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      reviewBusy = false;
    }
  }

  async function chooseThumbnail(name: string) {
    try {
      await selectJobThumbnail(selected, name);
      thumbnails = { ...thumbnails, selected: name };
      status = `Thumbnail ${name} selected.`;
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  function syncBroll(data: TimelineData) {
    const order: Record<string, number[]> = {};
    const approved: Record<string, number[]> = {};
    for (const [title, entries] of Object.entries(data.broll ?? {})) {
      const saved = data.broll_approval?.[title];
      order[title] = saved?.order?.length
        ? [...saved.order]
        : entries.map((_, index) => index);
      approved[title] = saved?.approved?.length
        ? [...saved.approved]
        : entries.map((_, index) => index);
    }
    brollOrder = order;
    brollApproved = approved;
  }

  function selectClip(clip: TimelineData["video"][number] | null) {
    selectedClip = clip;
    if (clip) {
      clipStart = clip.start_sec;
      clipEnd = clip.end_sec;
      clipDelta = 1;
      transitionType = (clip.transition as "crossfade" | "fade_to_black" | null) ?? "none";
      transitionFrames = clip.transition_frames || 6;
      clipScale = clip.zoom ?? 1;
      posX = clip.pos_x ?? 0;
      posY = clip.pos_y ?? 0;
      const audio = timeline?.audio.find((item) => item.id === clip.id);
      fadeIn = audio?.fade_in_sec ?? 0;
      fadeOut = audio?.fade_out_sec ?? 0;
    }
    editStatus = "";
  }

  async function saveClipStyle() {
    if (!selectedClip) return;
    styleBusy = true;
    error = "";
    try {
      const response = await updateTimelineClip(selected, selectedClip.id, {
        transition_type: transitionType,
        transition_duration_frames: transitionFrames,
        scale: clipScale,
        pos_x: posX,
        pos_y: posY,
        fade_in_sec: fadeIn,
        fade_out_sec: fadeOut
      });
      status = `Clip style saved at revision ${response.revision}.`;
      await loadTimeline(selectedClip.id);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      styleBusy = false;
    }
  }

  function seek(value: number) {
    const target = Math.max(0, Math.min(duration, value));
    playhead = target;
    if (videoEl && Number.isFinite(videoEl.duration)) {
      videoEl.currentTime = Math.min(target, Math.max(0, videoEl.duration - 0.01));
    }
  }

  function togglePlay() {
    if (!videoEl) return;
    if (videoEl.paused) {
      void videoEl.play();
    } else {
      videoEl.pause();
    }
  }

  function onPlay() {
    playing = true;
    cancelAnimationFrame(raf);
    const tick = () => {
      if (videoEl) playhead = videoEl.currentTime;
      if (videoEl && !videoEl.paused) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
  }

  function onPause() {
    playing = false;
    cancelAnimationFrame(raf);
  }

  async function buildPreview() {
    previewBusy = true;
    previewPercent = 0;
    previewMessage = "Queued";
    error = "";
    try {
      const payload = await createJobPreview(selected, true, true);
      const initial = typeof payload.status === "object" ? payload.status : null;
      if (initial) {
        previewPercent = initial.percent;
        previewMessage = initial.message ?? initial.status;
      }
      for (let attempt = 0; attempt < 600; attempt += 1) {
        if (attempt > 0) await new Promise((resolve) => setTimeout(resolve, 700));
        const current = await getPreviewStatus(selected);
        previewPercent = current.percent;
        previewMessage = current.message ?? current.status;
        if (current.status === "ready") {
          previewUrl = `${payload.url}?t=${Date.now()}`;
          status = "Browser preview rendered from the current timeline.";
          return;
        }
        if (current.status === "failed" || current.status === "cancelled") {
          error = current.error || `Preview ${current.status}.`;
          return;
        }
      }
      error = "Preview render timed out. Check the server log.";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      previewBusy = false;
    }
  }

  async function stopPreview() {
    try {
      await cancelPreview(selected);
      previewMessage = "Cancelling…";
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function applyEdit(
    action: "trim" | "move" | "delete" | "split" | "ripple",
    values: { start_sec?: number; end_sec?: number; delta_sec?: number; split_sec?: number } = {}
  ) {
    if (!selectedClip) return;
    editBusy = true;
    editStatus = "";
    error = "";
    try {
      const response = await editTimeline(selected, {
        clip_id: selectedClip.id,
        action,
        ...values
      });
      status = `Timeline revision ${response.revision} saved. ${response.warning}`;
      await loadTimeline(selectedClip.id);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      editBusy = false;
    }
  }

  function trimSelected() {
    if (!selectedClip) return;
    void applyEdit("trim", { start_sec: clipStart, end_sec: clipEnd });
  }

  function moveSelected() {
    if (!selectedClip) return;
    void applyEdit("move", { delta_sec: clipDelta });
  }

  function deleteSelected(ripple = false) {
    if (!selectedClip) return;
    void applyEdit(ripple ? "ripple" : "delete");
  }

  function splitSelected() {
    if (!selectedClip) return;
    void applyEdit("split", { split_sec: playhead });
  }

  async function undo() {
    editBusy = true;
    try {
      await undoTimeline(selected);
      await loadTimeline();
      status = "Undid the last timeline edit.";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      editBusy = false;
    }
  }

  async function redo() {
    editBusy = true;
    try {
      await redoTimeline(selected);
      await loadTimeline();
      status = "Redid the last timeline edit.";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      editBusy = false;
    }
  }

  function fitTimeline() {
    zoom = Math.max(18, Math.min(320, (1200 - 96) / duration));
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

  function toggleBroll(title: string, index: number) {
    const current = new Set(brollApproved[title] ?? []);
    if (current.has(index)) current.delete(index);
    else current.add(index);
    brollApproved = { ...brollApproved, [title]: [...current].sort((a, b) => a - b) };
  }

  function moveBroll(title: string, index: number, direction: -1 | 1) {
    const order = [...(brollOrder[title] ?? [])];
    const position = order.indexOf(index);
    const target = position + direction;
    if (position < 0 || target < 0 || target >= order.length) return;
    [order[position], order[target]] = [order[target], order[position]];
    brollOrder = { ...brollOrder, [title]: order };
  }

  async function saveBroll(title: string) {
    brollBusy = title;
    error = "";
    try {
      const approval = await approveBroll(selected, {
        title,
        approved: [...(brollApproved[title] ?? [])].sort((a, b) => a - b),
        order: brollOrder[title] ?? []
      });
      if (timeline) timeline = { ...timeline, broll_approval: approval };
      status = `B-roll approval saved for “${title}”.`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      brollBusy = "";
    }
  }

  function onKeydown(event: KeyboardEvent) {
    const target = event.target as HTMLElement | null;
    if (target && ["INPUT", "TEXTAREA", "SELECT"].includes(target.tagName)) return;
    if (event.code === "Space") {
      event.preventDefault();
      togglePlay();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      void (event.shiftKey ? redo() : undo());
      return;
    }
    if (!selectedClip) return;
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      deleteSelected(event.shiftKey);
    } else if (event.key.toLowerCase() === "s") {
      event.preventDefault();
      splitSelected();
    }
  }

  function entryLabel(entry: Record<string, unknown>, index: number): string {
    const path = String(entry.path ?? entry.source_url ?? "asset");
    const name = path.split(/[\\/]/).pop() ?? path;
    const provider = String(entry.provider ?? "local");
    const start = Number(entry.start_sec ?? 0);
    return `${index + 1}. ${name} · ${provider} · ${start.toFixed(1)}s`;
  }
</script>

<div class="space-y-4" data-testid="timeline-panel">
  <ErrorBanner message={error} onDismiss={() => (error = "")} testId="timeline-error" />

  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-sm font-semibold text-white">Timeline</h2>
        <p class="mt-1 text-xs text-neutral-500">
          Frame-accurate canvas editing over project_state.json. Drag clips, trim selected edges, split at the playhead, and undo safely.
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <select bind:value={selected} onchange={() => void loadTimeline()} class="max-w-[280px] rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-200">
          {#each jobs as job}
            <option value={job.job_id}>{job.result?.recipe_id ?? "recipe"} · {job.job_id.slice(0, 8)}</option>
          {/each}
        </select>
        <button type="button" onclick={() => void loadTimeline()} class="rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300 hover:border-sky-500">Refresh</button>
      </div>
    </div>
    {#if loading}<p class="mt-2 text-[11px] text-neutral-500">Loading timeline…</p>{/if}
    {#if !loading && !jobs.length}<p class="mt-2 text-[11px] text-neutral-500">Run a recipe to populate the timeline.</p>{/if}
    {#if status}<p class="mt-2 text-[11px] text-emerald-300" role="status">{status}</p>{/if}
  </section>

  {#if timeline}
    <section class="overflow-hidden rounded-2xl border border-neutral-800 bg-neutral-950">
      <div class="flex flex-wrap items-center gap-2 border-b border-neutral-800 px-3 py-2">
        <button type="button" onclick={togglePlay} disabled={!canPreview} class="rounded-lg border border-sky-500/40 bg-sky-500/10 px-3 py-1.5 text-[11px] text-sky-200 disabled:opacity-40">
          {playing ? "Pause" : "Play"}
        </button>
        <span class="rounded bg-neutral-900 px-2 py-1 font-mono text-[10px] text-neutral-300" data-testid="timeline-timecode">{timecode(playhead)}</span>
        <label class="flex items-center gap-1 font-mono text-[10px] text-neutral-600">
          <input
            type="number"
            min="0"
            max={duration}
            step="0.01"
            value={Math.round(playhead * 1000) / 1000}
            onchange={(event) => seek(Number(event.currentTarget.value))}
            class="w-20 rounded border border-neutral-800 bg-neutral-900 px-1.5 py-1 text-[10px] text-neutral-300"
            aria-label="Playhead seconds"
          />
          s · frame {Math.round(playhead * fps)}
        </label>
        <span class="mx-1 h-4 w-px bg-neutral-800"></span>
        <button type="button" onclick={() => void undo()} disabled={!timeline.can_undo || editBusy} class="rounded-lg border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 disabled:opacity-40">Undo</button>
        <button type="button" onclick={() => void redo()} disabled={!timeline.can_redo || editBusy} class="rounded-lg border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 disabled:opacity-40">Redo</button>
        <button type="button" onclick={splitSelected} disabled={!selectedClip || editBusy} class="rounded-lg border border-violet-500/40 px-2 py-1 text-[10px] text-violet-200 disabled:opacity-40" title="Split selected clip at playhead (S)">Split</button>
        <button type="button" onclick={() => deleteSelected(false)} disabled={!selectedClip || editBusy} class="rounded-lg border border-rose-500/40 px-2 py-1 text-[10px] text-rose-200 disabled:opacity-40" title="Delete selected clip (Delete)">Delete</button>
        <button type="button" onclick={() => deleteSelected(true)} disabled={!selectedClip || editBusy} class="rounded-lg border border-rose-500/30 px-2 py-1 text-[10px] text-rose-300 disabled:opacity-40" title="Delete and close the gap (Shift+Delete)">Ripple</button>
        <label class="ml-auto flex items-center gap-1.5 text-[10px] text-neutral-500">
          <input type="checkbox" bind:checked={snap} class="h-3.5 w-3.5 rounded border-neutral-700 bg-neutral-800" />
          Snap
        </label>
        <button type="button" onclick={fitTimeline} class="rounded-lg border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300">Fit</button>
        <label class="flex items-center gap-2 text-[10px] text-neutral-500">
          Zoom
          <input type="range" min="16" max="400" step="1" bind:value={zoom} class="w-24 accent-sky-400" />
          <span class="w-9 text-right font-mono text-neutral-400">{Math.round(zoom)}</span>
        </label>
      </div>

      <TimelineCanvas
        {timeline}
        {playhead}
        {zoom}
        selectedClipId={selectedClip?.id ?? ""}
        {snap}
        {brollApproved}
        onSeek={seek}
        onSelectClip={selectClip}
        onMoveClip={(id, delta) => {
          const clip = timeline?.video.find((item) => item.id === id) ?? null;
          if (clip) {
            selectClip(clip);
            void applyEdit("move", { delta_sec: delta });
          }
        }}
        onTrimClip={(id, start, end) => {
          const clip = timeline?.video.find((item) => item.id === id) ?? null;
          if (clip) {
            selectClip(clip);
            void applyEdit("trim", { start_sec: start, end_sec: end });
          }
        }}
        onZoom={(value) => (zoom = value)}
      />

      <div class="border-t border-neutral-800 p-3">
        <div class="grid gap-3 lg:grid-cols-[minmax(0,1fr)_320px]">
          <div class="space-y-3">
            {#if previewUrl}
              <video
                bind:this={videoEl}
                class="max-h-[420px] w-full rounded-xl border border-neutral-800 bg-black"
                controls
                preload="metadata"
                src={previewUrl}
                onplay={onPlay}
                onpause={onPause}
                onseeked={() => {
                  if (videoEl) playhead = videoEl.currentTime;
                }}
                ontimeupdate={() => {
                  if (videoEl && !videoEl.paused) playhead = videoEl.currentTime;
                }}
              >
                <track kind="captions" src="data:text/vtt;charset=utf-8,WEBVTT%0A%0A" />
              </video>
              <WaveformStrip url={previewUrl} {playhead} {duration} onSeek={seek} />
            {:else}
              <div class="flex min-h-[180px] flex-col items-center justify-center rounded-xl border border-dashed border-neutral-800 bg-black/40 p-4 text-center">
                <p class="text-xs text-neutral-400">No browser preview yet.</p>
                <p class="mt-1 text-[10px] text-neutral-600">Render one from the current timeline, or run a recipe that produces an MP4.</p>
                <button type="button" onclick={() => void buildPreview()} disabled={previewBusy || !selected} class="mt-3 rounded-lg border border-sky-500/40 px-3 py-1.5 text-[11px] text-sky-200 disabled:opacity-40">
                  {previewBusy ? "Rendering…" : "Render preview"}
                </button>
                {#if previewBusy}
                  <div class="mt-2 w-full max-w-sm">
                    <div class="h-1.5 overflow-hidden rounded-full bg-neutral-800">
                      <div class="h-full rounded-full bg-sky-400 transition-all" style={`width:${previewPercent}%`}></div>
                    </div>
                    <div class="mt-1 flex items-center justify-between text-[10px] text-neutral-500">
                      <span>{previewMessage || "Rendering"} · {previewPercent}%</span>
                      <button type="button" onclick={() => void stopPreview()} class="text-rose-300 hover:text-white">Cancel</button>
                    </div>
                  </div>
                {/if}
              </div>
            {/if}
          </div>

          <div class="space-y-2">
            <div class="rounded-xl border border-neutral-800 bg-neutral-900/40 p-3">
              <div class="flex items-center justify-between">
                <p class="text-[10px] uppercase tracking-wide text-neutral-500">Selected clip</p>
                <span class="font-mono text-[10px] text-neutral-600">rev {timeline.revision}</span>
              </div>
              {#if selectedClip}
                <p class="mt-1 break-all font-mono text-[11px] text-sky-200">{selectedClip.id}</p>
                <div class="mt-2 grid grid-cols-2 gap-2">
                  <label class="text-[10px] text-neutral-400">Timeline in
                    <input type="number" min="0" step="0.01" bind:value={clipStart} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
                  </label>
                  <label class="text-[10px] text-neutral-400">Timeline out
                    <input type="number" min="0" step="0.01" bind:value={clipEnd} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
                  </label>
                </div>
                <div class="mt-2 flex flex-wrap items-end gap-2">
                  <button type="button" onclick={trimSelected} disabled={editBusy} class="rounded border border-sky-500/40 px-2 py-1 text-[10px] text-sky-300 disabled:opacity-40">Trim</button>
                  <label class="text-[10px] text-neutral-400">Move (s)
                    <input type="number" step="0.1" bind:value={clipDelta} class="mt-1 block w-20 rounded border border-neutral-700 bg-neutral-950 px-2 py-1 text-[11px] text-neutral-100" />
                  </label>
                  <button type="button" onclick={moveSelected} disabled={editBusy} class="rounded border border-neutral-600 px-2 py-1 text-[10px] text-neutral-300 disabled:opacity-40">Move</button>
                </div>
                <div class="mt-3 grid grid-cols-2 gap-2 border-t border-neutral-800 pt-2">
                  <label class="text-[10px] text-neutral-400">Transition
                    <select bind:value={transitionType} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100">
                      <option value="none">cut</option>
                      <option value="crossfade">crossfade</option>
                      <option value="fade_to_black">fade to black</option>
                    </select>
                  </label>
                  <label class="text-[10px] text-neutral-400">Frames
                    <input type="number" min="1" max="120" step="1" bind:value={transitionFrames} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100" />
                  </label>
                  <label class="text-[10px] text-neutral-400">Scale
                    <input type="number" min="1" max="3" step="0.01" bind:value={clipScale} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100" />
                  </label>
                  <label class="text-[10px] text-neutral-400">Fade in (s)
                    <input type="number" min="0" max="30" step="0.05" bind:value={fadeIn} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100" />
                  </label>
                  <label class="text-[10px] text-neutral-400">Fade out (s)
                    <input type="number" min="0" max="30" step="0.05" bind:value={fadeOut} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100" />
                  </label>
                  <div class="flex items-end">
                    <button type="button" onclick={() => void saveClipStyle()} disabled={styleBusy} class="w-full rounded border border-sky-500/40 px-2 py-1 text-[10px] text-sky-300 disabled:opacity-40">{styleBusy ? "Saving…" : "Save style"}</button>
                  </div>
                </div>
                <p class="mt-2 text-[10px] text-neutral-500">
                  Transition: {selectedClip.transition ?? "cut"} · keyframes: {selectedClip.keyframes ?? 0} · zoom {selectedClip.zoom?.toFixed(2) ?? "1.00"}
                </p>
              {:else}
                <p class="mt-2 text-[10px] text-neutral-500">Select a clip on the canvas to inspect and edit it.</p>
              {/if}
              {#if editStatus}<p class="mt-1 text-[10px] text-amber-300">{editStatus}</p>{/if}
            </div>

            <div class="rounded-xl border border-neutral-800 bg-neutral-900/40 p-3">
              <p class="text-[10px] uppercase tracking-wide text-neutral-500">Captions</p>
              <div class="mt-2 max-h-44 space-y-1 overflow-auto">
                {#each timeline.captions as caption}
                  <button
                    type="button"
                    onclick={() => editCaption(caption)}
                    class={`block w-full truncate rounded px-2 py-1 text-left text-[10px] ${selectedCaption === caption.id ? "bg-violet-500/20 text-violet-100" : "text-neutral-400 hover:bg-neutral-800/60"}`}
                  >
                    {caption.start_sec.toFixed(1)}s · {caption.text}
                  </button>
                {/each}
                {#if !timeline.captions.length}<p class="text-[10px] text-neutral-600">No captions in this timeline.</p>{/if}
              </div>
              {#if selectedCaption !== null}
                <textarea rows="3" bind:value={captionDraft} class="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"></textarea>
                <div class="mt-2 flex items-center gap-2">
                  <button type="button" onclick={() => void saveCaption()} disabled={captionBusy} class="rounded border border-violet-500/40 px-2 py-1 text-[10px] text-violet-200 disabled:opacity-40">{captionBusy ? "Saving…" : "Save caption"}</button>
                  {#if captionStatus}<span class="text-[10px] text-neutral-400">{captionStatus}</span>{/if}
                </div>
              {/if}
            </div>
          </div>
        </div>
      </div>
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 class="text-xs font-semibold text-neutral-100">Shorts</h3>
          <p class="mt-1 text-[10px] text-neutral-500">Edit, reframe, caption, dub, and publish each Short from the current job.</p>
        </div>
        <span class="text-[10px] text-neutral-500">{timeline.shorts.length} Short(s)</span>
      </div>
      {#if timeline.shorts.length}
        <div class="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-3">
          {#each timeline.shorts as short, index}
            <div class="rounded-xl border border-neutral-800 bg-neutral-950/50 p-3">
              <p class="truncate text-[11px] font-medium text-sky-200">{short.title}</p>
              <p class="mt-1 text-[10px] text-neutral-500">{short.duration_sec.toFixed(1)}s · {short.aspect_ratio ?? "9:16"}</p>
              <button type="button" onclick={() => (shortEditor = { index, short })} class="mt-2 rounded border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 hover:border-sky-500/60 hover:text-sky-200">Edit Short</button>
            </div>
          {/each}
        </div>
      {:else}
        <p class="mt-2 text-[10px] text-neutral-500">This job has no Shorts.</p>
      {/if}
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 class="text-xs font-semibold text-neutral-100">B-roll approval</h3>
          <p class="mt-1 text-[10px] text-neutral-500">Approve, reject, and reorder planned B-roll before the Shorts render consumes it.</p>
        </div>
        <button type="button" onclick={() => void buildPreview()} disabled={previewBusy || !selected} class="rounded-lg border border-neutral-700 px-2.5 py-1 text-[10px] text-neutral-300 disabled:opacity-40">Rebuild preview</button>
      </div>
      {#if Object.keys(timeline.broll ?? {}).length}
        <div class="mt-3 grid gap-3 lg:grid-cols-2">
          {#each Object.entries(timeline.broll) as [title, entries]}
            <div class="rounded-xl border border-neutral-800 bg-neutral-950/50 p-3">
              <div class="flex items-center justify-between gap-2">
                <p class="truncate text-[11px] font-medium text-amber-200">{title}</p>
                <span class="text-[9px] text-neutral-500">{(brollApproved[title] ?? []).length}/{entries.length}</span>
              </div>
              <ul class="mt-2 space-y-1">
                {#each (brollOrder[title] ?? entries.map((_, index) => index)) as index}
                  <li class="flex items-center gap-2 rounded bg-neutral-900/70 px-2 py-1">
                    <input
                      type="checkbox"
                      checked={(brollApproved[title] ?? []).includes(index)}
                      onchange={() => toggleBroll(title, index)}
                      class="h-3.5 w-3.5 rounded border-neutral-700 bg-neutral-800"
                    />
                    <span class="min-w-0 flex-1 truncate text-[10px] text-neutral-300" title={entryLabel(entries[index], index)}>{entryLabel(entries[index], index)}</span>
                    <button type="button" onclick={() => moveBroll(title, index, -1)} class="rounded px-1 text-[10px] text-neutral-500 hover:text-white" aria-label="Move B-roll up">↑</button>
                    <button type="button" onclick={() => moveBroll(title, index, 1)} class="rounded px-1 text-[10px] text-neutral-500 hover:text-white" aria-label="Move B-roll down">↓</button>
                  </li>
                {/each}
              </ul>
              <button type="button" onclick={() => void saveBroll(title)} disabled={brollBusy === title} class="mt-2 rounded border border-amber-500/40 px-2 py-1 text-[10px] text-amber-200 disabled:opacity-40">
                {brollBusy === title ? "Saving…" : "Save approval"}
              </button>
            </div>
          {/each}
        </div>
      {:else}
        <p class="mt-2 text-[10px] text-neutral-500">This job has no B-roll plan. Add a <span class="font-mono">broll.plan</span> step to the recipe.</p>
      {/if}
    </section>

    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
      <div class="flex flex-wrap items-center justify-between gap-2">
        <div>
          <h3 class="text-xs font-semibold text-neutral-100">Deliverables</h3>
          <p class="mt-1 text-[10px] text-neutral-500">Review checklist, approval, and thumbnail variants from this run.</p>
        </div>
        <span class={`rounded-full px-2 py-0.5 text-[9px] uppercase ${reviewApproval.approved ? "bg-emerald-500/10 text-emerald-300" : "bg-amber-500/10 text-amber-300"}`}>
          {reviewApproval.approved ? "approved" : "pending review"}
        </span>
      </div>
      <div class="mt-3 grid gap-3 lg:grid-cols-2">
        <div class="rounded-xl border border-neutral-800 bg-neutral-950/50 p-3">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Review checks</p>
          {#if reviewChecks.length}
            <ul class="mt-2 space-y-1">
              {#each reviewChecks as check}
                <li class="flex items-center gap-2 text-[10px]">
                  <span class={check.ok ? "text-emerald-300" : "text-amber-300"}>{check.ok ? "✓" : "•"}</span>
                  <span class={check.ok ? "text-neutral-300" : "text-amber-200"}>{check.label}</span>
                </li>
              {/each}
            </ul>
          {:else}
            <p class="mt-2 text-[10px] text-neutral-600">No review.json in this run. Add a <span class="font-mono">review.queue</span> step.</p>
          {/if}
          <textarea rows="2" bind:value={reviewComment} placeholder="Review comment" class="mt-2 w-full rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-[11px] text-neutral-100"></textarea>
          <div class="mt-2 flex gap-2">
            <button type="button" onclick={() => void decideReview(true)} disabled={reviewBusy || !reviewChecks.length} class="rounded border border-emerald-500/40 px-2 py-1 text-[10px] text-emerald-200 disabled:opacity-40">Approve</button>
            <button type="button" onclick={() => void decideReview(false)} disabled={reviewBusy || !reviewChecks.length} class="rounded border border-rose-500/40 px-2 py-1 text-[10px] text-rose-200 disabled:opacity-40">Reject</button>
          </div>
        </div>
        <div class="rounded-xl border border-neutral-800 bg-neutral-950/50 p-3">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Thumbnail A/B</p>
          {#if thumbnails.variants.length}
            <div class="mt-2 grid grid-cols-3 gap-2">
              {#each thumbnails.variants as variant}
                <button type="button" onclick={() => void chooseThumbnail(variant)} class={`overflow-hidden rounded border ${thumbnails.selected === variant ? "border-sky-400 ring-1 ring-sky-400" : "border-neutral-800"}`}>
                  <img src={jobThumbnailUrl(selected, variant)} alt={variant} class="aspect-video w-full object-cover" />
                  <span class="block truncate px-1 py-0.5 text-[8px] text-neutral-400">{variant}</span>
                </button>
              {/each}
            </div>
          {:else}
            <p class="mt-2 text-[10px] text-neutral-600">No thumbnail variants. Add a <span class="font-mono">thumbnail.generate</span> step with <span class="font-mono">variants</span>.</p>
          {/if}
        </div>
      </div>
    </section>
  {/if}
</div>

{#if shortEditor}
  <ShortEditor
    jobId={selected}
    index={shortEditor.index}
    short={shortEditor.short}
    open={shortEditor !== null}
    allowExternal={false}
    allowedHosts=""
    onClose={() => (shortEditor = null)}
    onSaved={() => void loadTimeline()}
  />
{/if}
