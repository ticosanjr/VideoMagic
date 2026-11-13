<script lang="ts">
  import HelpTip from "$lib/HelpTip.svelte";
  import { onDestroy, onMount } from "svelte";
  import ErrorBanner from "$lib/ErrorBanner.svelte";
  import TimelineCanvas from "$lib/TimelineCanvas.svelte";
  import RecutCanvas from "$lib/RecutCanvas.svelte";
  import TimelinePlayer from "$lib/TimelinePlayer.svelte";
  import TimelineInspector from "$lib/TimelineInspector.svelte";
  import TimelineAssetRail from "$lib/timeline/TimelineAssetRail.svelte";
  import TimelineInactiveSegments from "$lib/timeline/TimelineInactiveSegments.svelte";
  import TimelineCaptionList from "$lib/timeline/TimelineCaptionList.svelte";
  import TimelineMarkerList from "$lib/timeline/TimelineMarkerList.svelte";
  import TimelineVariantCompare from "$lib/timeline/TimelineVariantCompare.svelte";
  import TimelineRecutSelection from "$lib/timeline/TimelineRecutSelection.svelte";
  import TimelineSelectedClip from "$lib/timeline/TimelineSelectedClip.svelte";
  import TimelineClipComments from "$lib/timeline/TimelineClipComments.svelte";
  import Modal from "$lib/ui/Modal.svelte";
  import { fitScrollLeft, fitZoom, followScrollLeft, groupTrimEdits, liveSegments, outputForSource, sourceForOutput } from "$lib/timelineView";
  import { formatSeconds } from "$lib/format";
  import ShortEditor from "$lib/ShortEditor.svelte";
  import Icon from "$lib/ui/Icon.svelte";
  import EmptyState from "$lib/EmptyState.svelte";
  import WaveformStrip from "$lib/WaveformStrip.svelte";
  import {
    ApiError,
    addTimelineComment,
    addTimelineOverlay,
    listAssets,
    removeTimelineOverlay,
    addTimelineMarker,
    getTimelineComments,
    removeTimelineComment,
    approveBroll,
    cancelPreview,
    cancelRender,
    createJobPreview,
    editTimeline,
    editTimelineBatch,
    deleteTimelineSnapshot,
    errorMessage,
    getJobReview,
    getJobThumbnails,
    getJobVariants,
    getLiveSourceStatus,
    importTimelineSnapshot,
    listTimelineSnapshots,
    loadTimelineSnapshot,
    prefetchJobFrames,
    prepareLiveSource,
    saveTimelineSnapshot,
    selectJobVariant,
    timelineSnapshotFileUrl,
    getPreviewStatus,
    getRenderStatus,
    getTimeline,
    jobFrameUrl,
    getClipWaveform,
    jobArtifactUrl,
    jobThumbnailUrl,
    previewFileUrl,
    listJobs,
    addReviewComment,
    decideJobReview,
    getReviewComments,
    getThumbnailMetrics,
    recordThumbnailMetric,
    selectJobThumbnail,
    redoTimeline,
    removeTimelineMarker,
    renderFileUrl,
    describeError,
    formatBackendDetail,
    startRender,
    undoTimeline,
    updateTimelineTrack,
    updateJobCaption,
    updateTimelineClip,
    updateTimelineClips,
    type AssetRecord,
    type Job,
    type TimelineComment,
    type TimelineOverlay,
    type LiveSourceState,
    type TimelineSnapshot,
    type TimelineData,
    type VariantComparison
  } from "$lib/api";

  let jobs = $state<Job[]>([]);
  let selected = $state("");
  let timeline = $state<TimelineData | null>(null);
  let loading = $state(false);
  let error = $state("");
  let errorDetail = $state("");
  let status = $state("");
  let playhead = $state(0);
  let playbackRate = $state(1);
  let inPoint = $state<number | null>(null);
  let outPoint = $state<number | null>(null);
  let copiedStyle = $state<Record<string, unknown> | null>(null);
  let batchTransitionType = $state<"none" | "crossfade" | "fade_to_black">("none");
  let batchTransitionFrames = $state(6);
  let batchFadeIn = $state(0);
  let batchFadeOut = $state(0);
  let batchScale = $state(1);
  let batchPosX = $state(0);
  let batchPosY = $state(0);
  let livePlayer = $state<{
    seekSource: (time: number) => void;
    seekOutput: (time: number) => void;
    getOutputTime: () => number;
    playPause: () => void;
    nextActive: () => void;
    previousActive: () => void;
  } | null>(null);
  let liveSource = $state<LiveSourceState | null>(null);
  let liveSourceTimer: ReturnType<typeof setTimeout> | undefined;
  let snapshotOpen = $state(false);
  let snapshotName = $state("");
  let snapshots = $state<TimelineSnapshot[]>([]);
  let snapshotBusy = $state(false);
  let variants = $state<VariantComparison | null>(null);
  let variantBusy = $state(false);

  async function loadVariants() {
    if (!selected) return;
    variantBusy = true;
    try {
      variants = await getJobVariants(selected);
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      variantBusy = false;
    }
  }

  async function pickWinner(name: string) {
    if (!selected) return;
    variantBusy = true;
    try {
      await selectJobVariant(selected, name);
      variants = await getJobVariants(selected);
      status = `Winner: ${name}`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      variantBusy = false;
    }
  }
  let zoom = $state(80);
  let timelineHeight = $state(540);
  let snap = $state(true);
  let selectedClip = $state<TimelineData["video"][number] | null>(null);
  let selectedIds = $state<string[]>([]);
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
  let thumbMetrics = $state<Array<{ name: string; impressions: number; clicks: number; ctr: number }>>([]);
  let reviewComments = $state<Array<{ author: string; text: string; time_sec: number | null; at: string }>>([]);
  let commentDraft = $state("");
  let markerLabel = $state("");
  let comments = $state<TimelineComment[]>([]);
  let overlays = $state<TimelineOverlay[]>([]);
  let frameUrl = $state("");
  let frameTimer: ReturnType<typeof setTimeout> | undefined;
  let seekTimer: ReturnType<typeof setTimeout> | undefined;
  let jobsTimer: ReturnType<typeof setInterval> | undefined;
  let assets = $state<AssetRecord[]>([]);
  let commentText = $state("");
  let commentBusy = $state(false);
  let clipMenu = $state<{ x: number; y: number; clipId: string } | null>(null);
  let renderBusy = $state(false);
  let renderPercent = $state(0);
  let renderMessage = $state("");
  let renderReady = $state(false);
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
  let waveforms = $state<Record<string, number[]>>({});
  let autoPreview = $state(true);
  let previewDirty = $state(false);
  let followPlayhead = $state(true);
  let previewHeight = $state(480);
  let previewInspectorWidth = $state(320);
  let viewMode = $state<"normal" | "recut">("normal");
  let selectedInactiveId = $state("");
  let inactiveStart = $state(0);
  let inactiveEnd = $state(0);
  let previewScheduled: ReturnType<typeof setTimeout> | undefined;
  let disposed = false;
  const waveformCache = new Map<string, number[]>();
  const POLL_MS = 1000;
  const POLL_DEADLINE_MS = 2 * 60 * 60 * 1000;

  const duration = $derived(Math.max(0.001, timeline?.duration_sec ?? 1));
  const fps = $derived(timeline?.fps ?? 30);
  const removedDuration = $derived(
    (timeline?.inactive ?? []).reduce(
      (total, item) => total + Math.max(0, item.video_end_sec - item.video_start_sec),
      0
    )
  );
  const previewVideoHeight = $derived(Math.max(160, previewHeight - 100));
  const segments = $derived(liveSegments(timeline?.video ?? [], fps));
  const recutPlayhead = $derived(sourceForOutput(segments, playhead));
  const clipUnderPlayhead = $derived(
    (timeline?.video ?? []).find(
      (clip) =>
        playhead > clip.start_sec &&
        playhead < clip.end_sec
    ) ?? null
  );
  const liveActive = $derived(
    Boolean(
      timeline?.live_eligible &&
        (!liveSource || liveSource.status === "ready")
    )
  );
  const previewJob = $derived(jobs.find((job) => job.job_id === selected));
  const previewArtifact = $derived(
    Object.entries(previewJob?.result?.artifacts ?? {}).find(
      ([name, path]) =>
        name === "mp4" ||
        name.endsWith("mp4") ||
        String(path).toLowerCase().endsWith(".mp4")
    )?.[0] ?? ""
  );
  const canPreview = $derived(Boolean(liveActive || previewUrl || previewArtifact));

  onMount(() => {
    try {
      const saved = localStorage.getItem("videoflow.timelineView");
      if (saved === "recut" || saved === "normal") viewMode = saved;
      const height = Number(localStorage.getItem("videoflow.timelineHeight") || "");
      if (Number.isFinite(height) && height >= 240) timelineHeight = height;
      const follow = localStorage.getItem("videoflow.followPlayhead");
      if (follow === "false") followPlayhead = false;
      const preview = Number(localStorage.getItem("videoflow.previewHeight") || "");
      if (Number.isFinite(preview) && preview >= 260) previewHeight = preview;
      const inspector = Number(
        localStorage.getItem("videoflow.previewInspectorWidth") || ""
      );
      if (Number.isFinite(inspector) && inspector >= 240) {
        previewInspectorWidth = inspector;
      }
    } catch {
      /* private mode */
    }
    void loadJobs();
    jobsTimer = setInterval(() => {
      if (!document.hidden) void loadJobs();
    }, 4000);
    window.addEventListener("keydown", onKeydown);
  });

  function setViewMode(mode: "normal" | "recut") {
    viewMode = mode;
    try {
      localStorage.setItem("videoflow.timelineView", mode);
    } catch {
      /* private mode */
    }
  }

  onDestroy(() => {
    disposed = true;
    window.removeEventListener("keydown", onKeydown);
    clearInterval(jobsTimer);
    clearTimeout(liveSourceTimer);
    cancelAnimationFrame(raf);
    clearTimeout(previewScheduled);
    clearTimeout(frameTimer);
    clearTimeout(seekTimer);
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
      const available = (await listJobs()).filter(
        (job) => job.status === "succeeded" || job.timeline_ready
      );
      jobs = available;
      if (!available.some((job) => job.job_id === selected) && available[0]) {
        selected = available[0].job_id;
        await loadTimeline();
      }
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function loadTimeline(
    keepClipId = "",
    options: { assets?: boolean; deliverables?: boolean } = {}
  ) {
    if (!selected) return;
    const { assets = true, deliverables = true } = options;
    loading = true;
    error = "";
    editStatus = "";
    try {
      const loaded = await getTimeline(selected);
      timeline = { ...loaded, markers: loaded.markers ?? [], tracks: loaded.tracks ?? {} };
      if (!keepClipId) playhead = 0;
      selectedCaption = null;
      selectedInactiveId = "";
      if (!keepClipId) selectedIds = [];
      comments = loaded.comments ?? [];
      overlays = loaded.overlays ?? [];
      if (assets) void loadAssets();
      const keep = keepClipId
        ? timeline.video.find((clip) => clip.id === keepClipId) ?? null
        : null;
      selectClip(keep);
      previewUrl = "";
      frameUrl = "";
      const jobId = selected;
      const artifacts = previewJob?.result?.artifacts ?? {};
      const mp4 = Object.entries(artifacts).find(
        ([name, path]) =>
          name === "mp4" ||
          name.endsWith("mp4") ||
          String(path).toLowerCase().endsWith(".mp4")
      );
      previewUrl = mp4 ? jobArtifactUrl(jobId, mp4[0]) : "";
      if (!keepClipId) previewDirty = false;
      if (keepClipId) renderReady = false;
      syncBroll(timeline);
      void loadWaveforms(timeline);
      if (!keepClipId) {
        void hydratePreview(jobId, timeline.revision);
        void hydrateRender(jobId);
      }
      void ensureLiveSource(jobId);
      if (deliverables) await loadDeliverables();
    } catch (reason) {
      error = errorMessage(reason);
      timeline = null;
    } finally {
      loading = false;
    }
  }

  async function ensureLiveSource(jobId: string) {
    clearTimeout(liveSourceTimer);
    if (!timeline?.live_eligible) {
      liveSource = null;
      return;
    }
    liveSource = timeline.live_source ?? null;
    if (liveSource?.status === "ready") return;
    if (liveSource?.status === "failed") return;
    try {
      if (liveSource?.status !== "preparing") {
        const prepared = await prepareLiveSource(jobId);
        if (!prepared?.status) {
          liveSource = null;
          return;
        }
        liveSource = prepared;
      }
      const poll = async () => {
        if (selected !== jobId) return;
        try {
          const status = await getLiveSourceStatus(jobId);
          if (!status?.status) {
            liveSource = null;
            return;
          }
          liveSource = status;
          if (status.status === "ready" || status.status === "failed") return;
        } catch {
          return;
        }
        liveSourceTimer = setTimeout(() => void poll(), 1200);
      };
      liveSourceTimer = setTimeout(() => void poll(), 300);
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function hydratePreview(jobId: string, revision: number) {
    try {
      const status = await getPreviewStatus(jobId);
      if (selected !== jobId) return;
      if (status.status === "ready") {
        previewUrl = `${previewFileUrl(jobId)}?t=${Date.now()}`;
        previewDirty = (status.revision ?? -1) !== revision;
      } else if (status.status === "failed" || status.status === "stale") {
        previewDirty = true;
      }
    } catch {
      // A missing preview is not an error; the render button remains available.
    }
  }

  async function hydrateRender(jobId: string) {
    try {
      const status = await getRenderStatus(jobId);
      if (selected === jobId) renderReady = status.status === "ready";
    } catch {
      // A missing render is not an error.
    }
  }

  async function loadWaveforms(data: TimelineData) {
    if (!selected) return;
    const jobId = selected;
    const entries = await Promise.all(
      data.audio.map(async (clip) => {
        const start = clip.source_in_sec ?? clip.start_sec;
        const end = clip.source_out_sec ?? clip.end_sec;
        const buckets = Math.max(40, Math.min(720, Math.round((end - start) * 60)));
        const key = `${jobId}:${start}:${end}:${buckets}`;
        const cached = waveformCache.get(key);
        if (cached) return [clip.id, cached] as const;
        try {
          const peaks = await getClipWaveform(jobId, start, end, buckets);
          const usable = peaks.some((value) => value > 0.01) ? peaks : [];
          waveformCache.set(key, usable);
          return [clip.id, usable] as const;
        } catch {
          return null;
        }
      })
    );
    const next: Record<string, number[]> = {};
    for (const entry of entries) {
      if (entry) next[entry[0]] = entry[1];
    }
    if (selected === jobId) waveforms = next;
  }

  function schedulePreview() {
    previewDirty = true;
    if (!autoPreview || !selected || !previewUrl) return;
    clearTimeout(previewScheduled);
    previewScheduled = setTimeout(() => {
      if (!previewBusy && previewDirty) void buildPreview();
    }, 1200);
  }

  async function loadDeliverables() {
    const [reviewResult, thumbResult, metricResult, commentResult] =
      await Promise.allSettled([
        getJobReview(selected),
        getJobThumbnails(selected),
        getThumbnailMetrics(selected),
        getReviewComments(selected)
      ]);
    if (reviewResult.status === "fulfilled") {
      const payload = (reviewResult.value.review ?? {}) as {
        checks?: Array<{ id: string; label: string; ok: boolean }>;
      };
      reviewChecks = payload.checks ?? [];
      reviewApproval = reviewResult.value.approval ?? {};
    } else {
      reviewChecks = [];
      reviewApproval = {};
    }
    thumbnails =
      thumbResult.status === "fulfilled"
        ? thumbResult.value
        : { variants: [], selected: "" };
    thumbMetrics = metricResult.status === "fulfilled" ? metricResult.value : [];
    reviewComments = commentResult.status === "fulfilled" ? commentResult.value : [];
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

  async function addComment() {
    if (!commentDraft.trim()) return;
    try {
      await addReviewComment(selected, {
        text: commentDraft.trim(),
        time_sec: playhead
      });
      commentDraft = "";
      reviewComments = await getReviewComments(selected);
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function bumpMetric(name: string, key: "impressions" | "clicks") {
    try {
      await recordThumbnailMetric(selected, name, { [key]: 1 });
      thumbMetrics = await getThumbnailMetrics(selected);
    } catch (reason) {
      error = errorMessage(reason);
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

  async function renderTimeline() {
    renderBusy = true;
    renderPercent = 0;
    renderMessage = "Queued";
    error = "";
    errorDetail = "";
    try {
      await startRender(selected);
      const deadline = Date.now() + POLL_DEADLINE_MS;
      while (!disposed && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
        if (disposed) return;
        const current = await getRenderStatus(selected);
        renderPercent = current.percent;
        renderMessage = current.message ?? current.status;
        if (current.status === "ready") {
          renderReady = true;
          status = "MP4 render ready.";
          return;
        }
        if (current.status === "failed" || current.status === "cancelled") {
          error = current.error || `Render ${current.status}.`;
          errorDetail =
            formatBackendDetail(current.error_details) || current.error || "";
          return;
        }
      }
      if (!disposed) {
        error = "The render is still running on the server. Check again later.";
      }
    } catch (reason) {
      error = errorMessage(reason);
      errorDetail = describeError(reason);
    } finally {
      renderBusy = false;
    }
  }

  async function stopRender() {
    try {
      await cancelRender(selected);
      renderMessage = "Cancelling…";
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function addMarker() {
    try {
      const markers = await addTimelineMarker(selected, {
        time_sec: playhead,
        label: markerLabel.trim() || `Marker ${Math.round(playhead * 10) / 10}s`
      });
      if (timeline) timeline = { ...timeline, markers };
      markerLabel = "";
      status = "Marker added.";
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function removeMarker(markerId: string) {
    try {
      const markers = await removeTimelineMarker(selected, markerId);
      if (timeline) timeline = { ...timeline, markers };
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function toggleTrack(track: string, key: "muted" | "solo" | "locked") {
    if (!timeline) return;
    const current = timeline.tracks?.[track] ?? { muted: false, solo: false, locked: false };
    try {
      const tracks = await updateTimelineTrack(selected, track, {
        ...current,
        [key]: !current[key]
      });
      timeline = { ...timeline, tracks };
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

  function selectClip(clip: TimelineData["video"][number] | null, additive = false) {
    if (!clip) {
      selectedClip = null;
      selectedIds = [];
      editStatus = "";
      return;
    }
    if (additive) {
      if (selectedIds.includes(clip.id)) {
        selectedIds = selectedIds.filter((id) => id !== clip.id);
        if (selectedIds.length === 0) {
          selectedClip = null;
          return;
        }
      } else {
        selectedIds = [...selectedIds, clip.id];
      }
    } else {
      selectedIds = [clip.id];
    }
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
      await loadTimeline(selectedClip.id, { assets: false, deliverables: false });
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      styleBusy = false;
    }
  }

  async function loadAssets() {
    try {
      assets = (await listAssets()).filter((asset) =>
        ["image", "video"].includes(asset.kind)
      );
    } catch {
      assets = [];
    }
  }

  async function dropAsset(asset: Record<string, unknown>, timeSec: number) {
    if (!selected) return;
    try {
      overlays = await addTimelineOverlay(selected, {
        asset_id: String(asset.id ?? ""),
        path: String(asset.path ?? ""),
        start_sec: Math.max(0, timeSec),
        duration_sec: 3,
        kind: asset.kind === "video" ? "video" : "image",
      });
      await loadTimeline(selectedClip?.id ?? "", { assets: false, deliverables: false });
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function removeOverlay(overlayId: string) {
    try {
      overlays = await removeTimelineOverlay(selected, overlayId);
      await loadTimeline(selectedClip?.id ?? "", { assets: false, deliverables: false });
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function refreshComments() {
    if (!selected) return;
    try {
      comments = await getTimelineComments(selected, selectedClip?.id ?? "");
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  async function addClipComment() {
    if (!selectedClip || !commentText.trim()) return;
    commentBusy = true;
    try {
      comments = await addTimelineComment(selected, {
        clip_id: selectedClip.id,
        text: commentText.trim()
      });
      commentText = "";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      commentBusy = false;
    }
  }

  async function removeClipComment(commentId: string) {
    try {
      comments = await removeTimelineComment(selected, commentId);
    } catch (reason) {
      error = errorMessage(reason);
    }
  }

  function prefetchFrames(target: number) {
    if (!selected) return;
    void prefetchJobFrames(selected, Math.max(0, target - 0.5), 6, 4, 180)
      .then((payload) => {
        for (const frame of payload.frames) {
          const image = new Image();
          image.src = frame.url;
        }
      })
      .catch(() => undefined);
  }

  function applyPlaybackRate() {
    if (videoEl) videoEl.playbackRate = playbackRate;
  }

  function setPlaybackRate(value: number) {
    playbackRate = Math.max(1, Math.min(3, Math.round(value * 2) / 2));
    applyPlaybackRate();
  }

  function seekSegment(direction: -1 | 1) {
    if (liveActive) {
      if (direction > 0) livePlayer?.nextActive();
      else livePlayer?.previousActive();
      return;
    }
    const clips = timeline?.video ?? [];
    if (!clips.length) return;
    let index = clips.findIndex(
      (clip) => playhead >= clip.start_sec && playhead < clip.end_sec
    );
    if (index < 0) index = 0;
    const current = clips[index];
    const target =
      direction > 0
        ? clips[Math.min(clips.length - 1, index + 1)].start_sec
        : playhead - current.start_sec > 0.75
          ? current.start_sec
          : clips[Math.max(0, index - 1)].start_sec;
    seek(target);
  }

  async function openSnapshots() {
    snapshotOpen = true;
    snapshotBusy = true;
    try {
      snapshots = await listTimelineSnapshots();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      snapshotBusy = false;
    }
  }

  async function saveVersion() {
    if (!selected) return;
    snapshotBusy = true;
    error = "";
    try {
      const saved = await saveTimelineSnapshot(selected, snapshotName.trim());
      snapshotName = "";
      snapshots = await listTimelineSnapshots();
      status = `Saved timeline version ${saved.name}.`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      snapshotBusy = false;
    }
  }

  async function loadVersion(snapshot: TimelineSnapshot) {
    if (!selected) return;
    snapshotBusy = true;
    error = "";
    try {
      const revision = await loadTimelineSnapshot(snapshot.id, selected);
      snapshotOpen = false;
      await loadTimeline("", { assets: false, deliverables: false });
      status = `Loaded ${snapshot.name} at revision ${revision}.`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      snapshotBusy = false;
    }
  }

  function useInRecipe(snapshot: TimelineSnapshot) {
    window.dispatchEvent(
      new CustomEvent("videoflow:use-timeline", {
        detail: { path: snapshot.path, name: snapshot.name }
      })
    );
    snapshotOpen = false;
    status = `Opening ${snapshot.name} in the recipe builder.`;
  }

  async function importVersion(event: Event) {
    const input = event.currentTarget as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    snapshotBusy = true;
    error = "";
    try {
      const payload = JSON.parse(await file.text()) as Record<string, unknown>;
      const imported = await importTimelineSnapshot(payload, file.name.replace(/\.json$/i, ""));
      snapshots = await listTimelineSnapshots();
      status = `Imported timeline ${imported.name}.`;
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      snapshotBusy = false;
      input.value = "";
    }
  }

  async function removeVersion(snapshot: TimelineSnapshot) {
    snapshotBusy = true;
    try {
      await deleteTimelineSnapshot(snapshot.id);
      snapshots = await listTimelineSnapshots();
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      snapshotBusy = false;
    }
  }

  function seek(value: number) {
    const target = Math.max(0, Math.min(duration, value));
    playhead = target;
    if (liveActive) livePlayer?.seekOutput(target);
    prefetchFrames(target);
    clearTimeout(frameTimer);
    frameTimer = setTimeout(() => {
      if (selected) frameUrl = jobFrameUrl(selected, target);
    }, 120);
    clearTimeout(seekTimer);
    seekTimer = setTimeout(() => {
      if (videoEl && Number.isFinite(videoEl.duration)) {
        videoEl.currentTime = Math.min(target, Math.max(0, videoEl.duration - 0.01));
      }
    }, 80);
  }

  function togglePlay() {
    if (liveActive) {
      const playerTime = livePlayer?.getOutputTime?.() ?? playhead;
      if (!playing && Math.abs(playerTime - playhead) > 0.05) {
        livePlayer?.seekOutput(playhead);
      }
      livePlayer?.playPause();
      return;
    }
    if (!videoEl) return;
    applyPlaybackRate();
    const startAt = Math.max(0, Math.min(duration, playhead));
    if (startAt >= duration - 0.01) {
      playhead = 0;
      videoEl.currentTime = 0;
    } else if (Math.abs(videoEl.currentTime - startAt) > 0.05) {
      videoEl.currentTime = startAt;
    }
    if (videoEl.paused) {
      void videoEl.play();
    } else {
      videoEl.pause();
    }
  }

  function onPlay() {
    playing = true;
    applyPlaybackRate();
    cancelAnimationFrame(raf);
    const tick = () => {
      if (videoEl) playhead = videoEl.currentTime;
      followCursor();
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
    errorDetail = "";
    try {
      const payload = await createJobPreview(selected, true, true);
      const initial = typeof payload.status === "object" ? payload.status : null;
      if (initial) {
        previewPercent = initial.percent;
        previewMessage = initial.message ?? initial.status;
      }
      const deadline = Date.now() + POLL_DEADLINE_MS;
      while (!disposed && Date.now() < deadline) {
        await new Promise((resolve) => setTimeout(resolve, POLL_MS));
        if (disposed) return;
        const current = await getPreviewStatus(selected);
        previewPercent = current.percent;
        previewMessage = current.message ?? current.status;
        if (current.status === "stale") {
          previewDirty = true;
          if (autoPreview) schedulePreview();
          return;
        }
        if (current.status === "ready") {
          previewUrl = `${payload.url}?t=${Date.now()}`;
          const currentRevision = current.revision ?? -1;
          previewDirty = currentRevision !== (timeline?.revision ?? -1);
          status = previewDirty
            ? "Preview rendered, but newer edits are pending."
            : "Browser preview rendered from the current timeline.";
          if (previewDirty && autoPreview) schedulePreview();
          return;
        }
        if (current.status === "failed" || current.status === "cancelled") {
          error = current.error || `Preview ${current.status}.`;
          errorDetail =
            formatBackendDetail(current.error_details) || current.error || "";
          return;
        }
      }
      if (!disposed) {
        error = "The preview is still rendering on the server. Check again later.";
      }
    } catch (reason) {
      error = errorMessage(reason);
      errorDetail = describeError(reason);
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

  const selectedInactive = $derived(
    timeline?.inactive.find((item) => item.id === selectedInactiveId) ?? null
  );

  $effect(() => {
    const item = selectedInactive;
    if (!item) return;
    inactiveStart = item.video_start_sec;
    inactiveEnd = item.video_end_sec;
  });

  function selectRecut(kind: "active" | "inactive", id: string) {
    if (kind === "active") {
      selectedInactiveId = "";
      selectClip(timeline?.video.find((clip) => clip.id === id) ?? null);
      return;
    }
    selectedInactiveId = id;
    selectedClip = null;
    selectedIds = [];
  }

  function recutSeek(source: number) {
    seek(outputForSource(segments, source));
  }

  async function toggleSegment(id: string, makeActive: boolean) {
    if (!timeline || editBusy) return;
    editBusy = true;
    error = "";
    errorDetail = "";
    try {
      const response = await editTimeline(selected, timeline.revision, {
        clip_id: id,
        action: makeActive ? "activate" : "deactivate"
      });
      status = makeActive
        ? `Activated ${id} at revision ${response.revision}.`
        : `Deactivated ${id} at revision ${response.revision}.`;
      const keepPlayhead = playhead;
      await loadTimeline(id, { assets: false, deliverables: false });
      playhead = keepPlayhead;
      selectedInactiveId = makeActive ? "" : id;
      schedulePreview();
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "precondition_failed") {
        await loadTimeline("", { assets: false, deliverables: false });
        error = "The timeline changed in another window. Reloaded the latest revision.";
      } else {
        error = errorMessage(reason);
        errorDetail = describeError(reason);
      }
    } finally {
      editBusy = false;
    }
  }

  async function trimInactiveRange(id: string, start: number, end: number) {
    if (!timeline || editBusy) return;
    if (!(end > start)) {
      error = "The cut end must be after its start.";
      return;
    }
    editBusy = true;
    error = "";
    errorDetail = "";
    try {
      const response = await editTimeline(selected, timeline.revision, {
        clip_id: id,
        action: "recut",
        start_sec: start,
        end_sec: end
      });
      status = `Recut boundary saved at revision ${response.revision}. ${response.warning}`;
      await loadTimeline("", { assets: false, deliverables: false });
      selectedInactiveId = id;
      schedulePreview();
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "precondition_failed") {
        await loadTimeline("", { assets: false, deliverables: false });
        error = "The timeline changed in another window. Reloaded the latest revision.";
      } else {
        error = errorMessage(reason);
        errorDetail = describeError(reason);
      }
    } finally {
      editBusy = false;
    }
  }

  async function applyEdit(
    action:
      | "trim"
      | "move"
      | "delete"
      | "split"
      | "ripple"
      | "ripple_trim"
      | "slip"
      | "slide"
      | "duplicate",
    values: { start_sec?: number; end_sec?: number; delta_sec?: number; split_sec?: number } = {}
  ) {
    if (!selectedClip) return;
    editBusy = true;
    editStatus = "";
    error = "";
    try {
      const response = await editTimeline(selected, timeline?.revision, {
        clip_id: selectedClip.id,
        action,
        ...values
      });
      status = `Timeline revision ${response.revision} saved. ${response.warning}`;
      await loadTimeline(selectedClip.id, { assets: false, deliverables: false });
      schedulePreview();
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "precondition_failed") {
        await loadTimeline(selectedClip?.id ?? "", { assets: false, deliverables: false });
        error = "The timeline changed in another window. Reloaded the latest revision.";
      } else {
        error = errorMessage(reason);
      }
    } finally {
      editBusy = false;
    }
  }

  async function applyBatch(edits: Array<Record<string, unknown>>) {
    editBusy = true;
    error = "";
    try {
      const response = await editTimelineBatch(selected, timeline?.revision, edits as never);
      status = `Batch applied to ${response.applied} clip(s) at revision ${response.revision}.`;
      await loadTimeline(selectedClip?.id ?? "", { assets: false, deliverables: false });
      schedulePreview();
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "precondition_failed") {
        await loadTimeline(selectedClip?.id ?? "", { assets: false, deliverables: false });
        error = "The timeline changed in another window. Reloaded the latest revision.";
      } else {
        error = errorMessage(reason);
      }
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
    if (selectedIds.length > 1) {
      void applyBatch(
        selectedIds.map((id) => ({
          clip_id: id,
          action: "move",
          delta_sec: clipDelta
        }))
      );
    } else {
      void applyEdit("move", { delta_sec: clipDelta });
    }
  }

  function deleteSelected(ripple = false) {
    const ids = selectedIds.length ? selectedIds : selectedClip ? [selectedClip.id] : [];
    if (!ids.length) return;
    if (ids.length > 1) {
      void applyBatch(
        ids.map((id) => ({
          clip_id: id,
          action: ripple ? "ripple" : "delete"
        }))
      );
    } else if (selectedClip) {
      void applyEdit(ripple ? "ripple" : "delete");
    }
  }

  function splitSelected() {
    const clip = selectedClip ?? clipUnderPlayhead;
    if (!clip) {
      error = "Select a clip or move the playhead over one before splitting.";
      return;
    }
    if (clip !== selectedClip) selectClip(clip);
    const minimum = 1 / Math.max(1, fps);
    const inside =
      playhead > clip.start_sec + minimum &&
      playhead < clip.end_sec - minimum;
    const split = inside ? playhead : (clip.start_sec + clip.end_sec) / 2;
    playhead = split;
    status = inside
      ? `Splitting ${clip.id} at ${split.toFixed(2)}s.`
      : `Playhead moved to the middle of ${clip.id} to split.`;
    void applyEdit("split", { split_sec: split });
  }

  async function undo() {
    editBusy = true;
    try {
      await undoTimeline(selected);
      await loadTimeline("", { assets: false, deliverables: false });
      schedulePreview();
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
      await loadTimeline("", { assets: false, deliverables: false });
      schedulePreview();
      status = "Redid the last timeline edit.";
    } catch (reason) {
      error = errorMessage(reason);
    } finally {
      editBusy = false;
    }
  }

  function jumpMarker(direction: -1 | 1) {
    const markers = [...(timeline?.markers ?? [])].sort(
      (left, right) => left.time_sec - right.time_sec
    );
    if (!markers.length) return;
    let target: { time_sec: number } | undefined;
    if (direction > 0) {
      target = markers.find((marker) => {
        return marker.time_sec > playhead + 0.01;
      });
    } else {
      target = [...markers].reverse().find((marker) => {
        return marker.time_sec < playhead - 0.01;
      });
    }
    if (target) seek(target.time_sec);
  }

  function markIn() {
    inPoint = playhead;
    if (outPoint !== null && outPoint <= inPoint) outPoint = null;
    status = `In mark at ${playhead.toFixed(2)}s.`;
  }

  function markOut() {
    outPoint = playhead;
    if (inPoint !== null && inPoint >= outPoint) inPoint = null;
    status = `Out mark at ${playhead.toFixed(2)}s.`;
  }

  function clearMarks() {
    inPoint = null;
    outPoint = null;
    status = "In/out marks cleared.";
  }

  function beginTimelineResize(event: PointerEvent) {
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = timelineHeight;
    const move = (moveEvent: PointerEvent) => {
      timelineHeight = Math.max(260, Math.min(900, startHeight + moveEvent.clientY - startY));
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      try {
        localStorage.setItem("videoflow.timelineHeight", String(Math.round(timelineHeight)));
      } catch {
        /* private mode */
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up, { once: true });
  }

  function beginPreviewHeightResize(event: PointerEvent) {
    event.preventDefault();
    const startY = event.clientY;
    const startHeight = previewHeight;
    const move = (moveEvent: PointerEvent) => {
      previewHeight = Math.max(
        260,
        Math.min(900, startHeight + moveEvent.clientY - startY)
      );
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      try {
        localStorage.setItem("videoflow.previewHeight", String(Math.round(previewHeight)));
      } catch {
        /* private mode */
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up, { once: true });
  }

  function beginInspectorResize(event: PointerEvent) {
    event.preventDefault();
    const startX = event.clientX;
    const startWidth = previewInspectorWidth;
    const move = (moveEvent: PointerEvent) => {
      previewInspectorWidth = Math.max(
        240,
        Math.min(640, startWidth - (moveEvent.clientX - startX))
      );
    };
    const up = () => {
      window.removeEventListener("pointermove", move);
      try {
        localStorage.setItem(
          "videoflow.previewInspectorWidth",
          String(Math.round(previewInspectorWidth))
        );
      } catch {
        /* private mode */
      }
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up, { once: true });
  }

  function resetPreviewLayout() {
    previewHeight = 480;
    previewInspectorWidth = 320;
    try {
      localStorage.setItem("videoflow.previewHeight", "480");
      localStorage.setItem("videoflow.previewInspectorWidth", "320");
    } catch {
      /* private mode */
    }
  }

  function fitScroller(): HTMLElement | null {
    return document.querySelector<HTMLElement>(
      viewMode === "recut" ? '[data-testid="recut-scroller"]' : '[data-testid="timeline-scroller"]'
    );
  }

  function fitHeaderWidth(): number {
    return viewMode === "recut" ? 88 : 96;
  }

  function fitTimeline() {
    const viewport = fitScroller()?.clientWidth ?? 1200;
    const span =
      viewMode === "recut"
        ? Math.max(0.1, timeline?.source_duration_sec ?? duration)
        : duration;
    zoom = fitZoom(span, viewport, fitHeaderWidth());
    requestAnimationFrame(() => {
      const scroller = fitScroller();
      if (scroller) scroller.scrollLeft = 0;
    });
  }

  function setFollowPlayhead(value: boolean) {
    followPlayhead = value;
    try {
      localStorage.setItem("videoflow.followPlayhead", String(value));
    } catch {
      /* private mode */
    }
  }

  function followCursor() {
    if (!followPlayhead || !playing) return;
    const scroller = fitScroller();
    if (!scroller) return;
    const cursor = viewMode === "recut" ? recutPlayhead : playhead;
    const next = followScrollLeft(
      cursor,
      zoom,
      scroller.scrollLeft,
      scroller.clientWidth,
      fitHeaderWidth()
    );
    if (Math.abs(next - scroller.scrollLeft) > 1) scroller.scrollLeft = next;
  }

  function fitSelection() {
    const recut = viewMode === "recut";
    let start = 0;
    let end = recut ? Math.max(0.1, timeline?.source_duration_sec ?? duration) : duration;
    if (recut && selectedInactiveId) {
      const item = (timeline?.inactive ?? []).find((entry) => entry.id === selectedInactiveId);
      if (item) {
        start = item.video_start_sec;
        end = item.video_end_sec;
      }
    } else if (recut && selectedClip) {
      const clip = selectedClip;
      const segment = segments.find((entry) => entry.id === clip.id);
      if (segment) {
        start = segment.start;
        end = segment.end;
      }
    } else {
      const clips = (timeline?.video ?? []).filter(
        (clip) => selectedIds.includes(clip.id) || clip.id === selectedClip?.id
      );
      if (clips.length) {
        start = Math.min(...clips.map((clip) => clip.start_sec));
        end = Math.max(...clips.map((clip) => clip.end_sec));
      }
    }
    const span = Math.max(0.1, end - start);
    const viewport = fitScroller()?.clientWidth ?? 1200;
    zoom = fitZoom(span, viewport, fitHeaderWidth());
    requestAnimationFrame(() => {
      const scroller = fitScroller();
      if (scroller) scroller.scrollLeft = fitScrollLeft(start, zoom);
    });
  }

  async function deactivateSelected() {
    if (!selected || !selectedIds.length) return;
    await applyBatch(
      selectedIds.map((id) => ({ clip_id: id, action: "deactivate" })) as never
    );
  }

  function copyClipStyle() {
    if (!selectedClip) return;
    copiedStyle = {
      transition_type: selectedClip.transition ?? "none",
      transition_duration_frames: selectedClip.transition_frames || 6,
      scale: selectedClip.zoom ?? 1,
      pos_x: selectedClip.pos_x ?? 0,
      pos_y: selectedClip.pos_y ?? 0,
      fade_in_sec: selectedClip.fade_in_sec ?? 0,
      fade_out_sec: selectedClip.fade_out_sec ?? 0
    };
    status = `Copied style from ${selectedClip.id}.`;
  }

  async function applyStyleToSelection(
    ids: string[],
    payload: Parameters<typeof updateTimelineClips>[2],
    label: string
  ) {
    if (!selected || !ids.length) return;
    styleBusy = true;
    error = "";
    try {
      const result = await updateTimelineClips(selected, ids, payload);
      status = `${label} to ${result.applied} clip(s) at revision ${result.revision}.`;
      await loadTimeline(selectedClip?.id ?? "", {
        assets: false,
        deliverables: false
      });
      schedulePreview();
    } catch (reason) {
      if (reason instanceof ApiError && reason.code === "precondition_failed") {
        await loadTimeline(selectedClip?.id ?? "", {
          assets: false,
          deliverables: false
        });
        error = "The timeline changed in another window. Reloaded the latest revision.";
      } else {
        error = errorMessage(reason);
      }
    } finally {
      styleBusy = false;
    }
  }

  async function applyBatchStyle() {
    if (!selected || !selectedIds.length) return;
    await applyStyleToSelection(
      selectedIds,
      {
        transition_type: batchTransitionType,
        transition_duration_frames: Math.max(1, Math.round(batchTransitionFrames)),
        fade_in_sec: Math.max(0, batchFadeIn),
        fade_out_sec: Math.max(0, batchFadeOut),
        scale: Math.max(1, Math.min(3, batchScale)),
        pos_x: Math.max(-1, Math.min(1, batchPosX)),
        pos_y: Math.max(-1, Math.min(1, batchPosY))
      },
      "Applied batch style"
    );
  }

  async function resetBatchTransform() {
    if (!selected || !selectedIds.length) return;
    batchScale = 1;
    batchPosX = 0;
    batchPosY = 0;
    await applyStyleToSelection(
      selectedIds,
      { scale: 1, pos_x: 0, pos_y: 0 },
      "Reset transform"
    );
  }

  async function pasteClipStyle() {
    if (!copiedStyle || !selected) return;
    const ids = selectedIds.length ? selectedIds : selectedClip ? [selectedClip.id] : [];
    if (!ids.length) return;
    await applyStyleToSelection(
      ids,
      copiedStyle as Parameters<typeof updateTimelineClips>[2],
      "Pasted style"
    );
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
    const key = event.key.toLowerCase();
    if ((event.ctrlKey || event.metaKey) && key === "z") {
      event.preventDefault();
      void (event.shiftKey ? redo() : undo());
      return;
    }
    if ((event.ctrlKey || event.metaKey) && key === "s") {
      event.preventDefault();
      void saveVersion();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && key === "o") {
      event.preventDefault();
      void openSnapshots();
      return;
    }
    if (event.code === "Space" || key === "k") {
      event.preventDefault();
      togglePlay();
      return;
    }
    if (key === "j" && event.shiftKey) {
      event.preventDefault();
      seekSegment(-1);
      return;
    }
    if (key === "l" && event.shiftKey) {
      event.preventDefault();
      seekSegment(1);
      return;
    }
    if (key === "j") {
      event.preventDefault();
      seek(playhead - (event.repeat ? 2 : 1));
      return;
    }
    if (key === "l") {
      event.preventDefault();
      seek(playhead + (event.repeat ? 2 : 1));
      return;
    }
    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      if (event.altKey) {
        jumpMarker(event.key === "ArrowRight" ? 1 : -1);
        return;
      }
      const delta = event.shiftKey ? 1 : 1 / Math.max(1, fps);
      seek(playhead + (event.key === "ArrowRight" ? delta : -delta));
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      seek(0);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      seek(duration);
      return;
    }
    if (key === "f") {
      event.preventDefault();
      if (event.shiftKey) fitSelection();
      else fitTimeline();
      return;
    }
    if (key === "i") {
      event.preventDefault();
      markIn();
      return;
    }
    if (key === "o") {
      event.preventDefault();
      markOut();
      return;
    }
    if (key === "+" || key === "=") {
      event.preventDefault();
      zoom = Math.min(400, zoom * 1.18);
      return;
    }
    if (key === "-") {
      event.preventDefault();
      zoom = Math.max(16, zoom / 1.18);
      return;
    }
    if (key === "[") {
      event.preventDefault();
      setPlaybackRate(playbackRate - 0.5);
      return;
    }
    if (key === "]") {
      event.preventDefault();
      setPlaybackRate(playbackRate + 0.5);
      return;
    }
    if (key === "m") {
      event.preventDefault();
      void addMarker();
      return;
    }
    if (key === "x") {
      if (selectedInactiveId) {
        event.preventDefault();
        void toggleSegment(selectedInactiveId, true);
        return;
      }
      if (selectedClip) {
        event.preventDefault();
        void toggleSegment(selectedClip.id, false);
        return;
      }
    }
    if (event.key === "Delete" || event.key === "Backspace") {
      if (!selectedClip && !selectedIds.length) return;
      event.preventDefault();
      deleteSelected(event.shiftKey);
      return;
    }
    if (key === "s") {
      if (!selectedClip && !clipUnderPlayhead) return;
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

<div class="flex flex-col gap-4" data-testid="timeline-panel">
  <ErrorBanner message={error} detail={errorDetail} onDismiss={() => { error = ""; errorDetail = ""; }} testId="timeline-error" />

  <section class="rounded-2xl border border-neutral-800 bg-neutral-900/50 p-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <div class="flex items-center gap-1.5"><h2 class="text-sm font-semibold text-white">Timeline</h2> <HelpTip label="Edit" body="Edit the canonical project state: trim, move, split, slip, slide, overlays, comments, preview, and exports." doc="docs/timeline.md" /></div>
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
        <button type="button" onclick={() => void openSnapshots()} disabled={!selected} class="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-700 text-neutral-300 disabled:opacity-40" title="Saved timeline versions (Ctrl+O)" aria-label="Saved timeline versions"><Icon name="folder" size={14} /></button>
        <button type="button" onclick={() => void saveVersion()} disabled={!selected || snapshotBusy} class="flex h-8 w-8 items-center justify-center rounded-lg border border-emerald-500/40 text-emerald-200 disabled:opacity-40" title="Save timeline version (Ctrl+S)" aria-label="Save timeline version"><Icon name="save" size={14} /></button>
        <button type="button" onclick={() => void loadTimeline()} class="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-700 text-neutral-300" title="Refresh timeline" aria-label="Refresh timeline"><Icon name="refresh" size={14} /></button>
      </div>
    </div>
    {#if loading}<p class="mt-2 text-[length:var(--vf-text-xs)] text-neutral-500">Loading timeline…</p>{/if}
    {#if status}<p class="mt-2 text-[length:var(--vf-text-xs)] text-emerald-300" role="status">{status}</p>{/if}
  </section>

  {#if !loading && !jobs.length}
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4" data-testid="timeline-empty">
      <EmptyState
        title="No runs to edit yet"
        description="Run a recipe from Produce. When a recipe produces a timeline, it appears here for frame-accurate editing."
        action="Open Produce"
        icon="film"
        onaction={() => (window.location.hash = "#overview")}
      />
    </section>
  {/if}

  {#if !timeline && (loading || (!error && jobs.length))}
    <section class="rounded-2xl border border-neutral-800 bg-neutral-900/40 p-4" aria-busy="true" data-testid="timeline-loading">
      <div class="animate-pulse space-y-3">
        <div class="h-[340px] rounded-xl border border-neutral-800 bg-neutral-950/80"></div>
        <div class="flex gap-2">
          <div class="h-8 w-8 rounded-lg bg-neutral-800"></div>
          <div class="h-8 w-8 rounded-lg bg-neutral-800"></div>
          <div class="h-8 w-8 rounded-lg bg-neutral-800"></div>
          <div class="h-8 flex-1 rounded-lg bg-neutral-800/60"></div>
        </div>
        <div class="h-[220px] rounded-xl border border-neutral-800 bg-neutral-950/70"></div>
      </div>
      <p class="mt-2 text-[11px] text-neutral-500">Loading the timeline and active segments…</p>
    </section>
  {/if}

  {#if timeline}
      <div class="flex flex-col gap-4">
      <div class="mb-2 rounded-2xl border border-neutral-800 bg-neutral-900/40 p-3" data-testid="timeline-preview">
        <div class="mb-2 flex flex-wrap items-center gap-3 text-[10px] text-neutral-400" data-testid="preview-durations">
          <button type="button" onclick={resetPreviewLayout} class="rounded border border-neutral-700 px-2 py-0.5 text-[9px] text-neutral-400 hover:text-neutral-200">Reset layout</button>
          <span>Source total <b class="font-mono text-neutral-200">{formatSeconds(timeline.source_duration_sec)}</b></span>
          <span>Edited <b class="font-mono text-emerald-200">{formatSeconds(timeline.duration_sec)}</b></span>
          <span>Removed <b class="font-mono text-rose-200">{formatSeconds(removedDuration)}</b></span>
        </div>
        <div
          class="grid gap-3 lg:h-[var(--preview-h)] lg:grid-cols-[minmax(0,1fr)_var(--inspector-w)]"
          style={`--preview-h:${previewHeight}px;--inspector-w:${previewInspectorWidth}px`}
        >
          <div class="relative space-y-3 lg:h-full lg:min-h-0 lg:overflow-y-auto">
            <div class="absolute -right-2 top-0 z-10 h-full w-3 cursor-col-resize rounded bg-transparent hover:bg-sky-400/30" role="separator" aria-label="Resize preview width" data-testid="preview-width-resize" onpointerdown={beginInspectorResize}></div>
            {#if liveActive}
              <TimelinePlayer
                bind:this={livePlayer}
                jobId={selected}
                {timeline}
                streamUrl={liveSource?.url ?? ""}
                bind:rate={playbackRate}
                controls={false}
                height={previewVideoHeight}
                ontime={(_source, output) => {
                  playhead = output;
                  followCursor();
                }}
                onstate={(value) => (playing = value)}
              />
            {:else if timeline.live_eligible && liveSource?.status === "preparing" && !previewUrl}
              <div class="flex h-[340px] items-center justify-center rounded-xl border border-sky-500/20 bg-sky-950/20 text-[11px] text-sky-200" data-testid="live-preparing">
                <span class="mr-2 h-3 w-3 animate-spin rounded-full border-2 border-sky-300 border-r-transparent"></span>
                Preparing browser-safe live playback…
              </div>
            {:else if timeline.live_eligible && liveSource?.status === "failed" && !previewUrl}
              <div class="flex h-[340px] flex-col items-center justify-center rounded-xl border border-amber-400/20 bg-amber-950/20 p-4 text-center text-[11px] text-amber-200" data-testid="live-fallback">
                <p>Live playback unavailable: {liveSource.error || liveSource.reason}.</p>
                <p class="mt-1 text-[10px] text-amber-200/70">Rendering the browser preview instead.</p>
              </div>
            {:else if previewUrl}
              <video
                bind:this={videoEl}
                class="w-full rounded-xl border border-neutral-800 bg-black object-contain"
                style={`height:${previewVideoHeight}px`}
                controls
                preload="metadata"
                src={previewUrl}
                onplay={onPlay}
                onpause={onPause}
                onloadedmetadata={applyPlaybackRate}
                onseeked={() => {
                  if (videoEl) playhead = videoEl.currentTime;
                }}
                ontimeupdate={() => {
                  if (videoEl && !videoEl.paused) {
                    playhead = videoEl.currentTime;
                    followCursor();
                  }
                }}
              >
                <track kind="captions" src="data:text/vtt;charset=utf-8,WEBVTT%0A%0A" />
              </video>
              <WaveformStrip url={previewUrl} {playhead} {duration} onSeek={seek} />
              {#if frameUrl}
                <figure class="mt-2">
                  <img src={frameUrl} alt="Frame at the playhead" class="max-h-[240px] w-full rounded-xl border border-neutral-800 bg-black object-contain" />
                  <figcaption class="mt-1 text-[10px] text-neutral-500">Frame at {playhead.toFixed(2)}s · frame {Math.round(playhead * fps)}</figcaption>
                </figure>
              {/if}
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

          <TimelineInspector class="lg:h-full">
            {#snippet inspect()}
            {#if timeline}
            
            <TimelineSelectedClip
              clip={selectedClip}
              revision={timeline.revision}
              bind:start={clipStart}
              bind:end={clipEnd}
              bind:delta={clipDelta}
              {editBusy}
              {editStatus}
              onTrim={trimSelected}
              onMove={moveSelected}
            />

            <TimelineInactiveSegments
              inactive={timeline.inactive}
              onSelect={(id) => selectRecut("inactive", id)}
              onActivate={(id) => void toggleSegment(id, true)}
            />

            <TimelineCaptionList
              captions={timeline.captions}
              {selectedCaption}
              bind:draft={captionDraft}
              busy={captionBusy}
              status={captionStatus}
              onSelect={editCaption}
              onSave={saveCaption}
            />

            <TimelineMarkerList
              markers={timeline.markers}
              onSeek={seek}
              onRemove={(id) => void removeMarker(id)}
            />

            <TimelineClipComments
              {comments}
              {overlays}
              clip={selectedClip}
              fps={timeline.fps}
              bind:commentText
              {commentBusy}
              onAddComment={addClipComment}
              onRemoveComment={(id) => void removeClipComment(id)}
              onRemoveOverlay={(id) => void removeOverlay(id)}
            />
            {/if}
            {/snippet}
            {#snippet effects()}
              {#if selectedIds.length > 1}
              <div class="rounded-xl border border-sky-500/30 bg-sky-950/20 p-3" data-testid="multi-selection">
                <p class="text-[10px] uppercase tracking-wide text-sky-300">{selectedIds.length} clips selected</p>
                <div class="mt-2 flex flex-wrap gap-1">
                  <button type="button" onclick={fitSelection} class="rounded border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300">Fit selection</button>
                  <button type="button" onclick={() => void deactivateSelected()} disabled={editBusy} class="rounded border border-rose-500/40 px-2 py-1 text-[10px] text-rose-200 disabled:opacity-40">Deactivate selected</button>
                  <button type="button" onclick={() => void pasteClipStyle()} disabled={!copiedStyle || styleBusy} class="rounded border border-sky-500/40 px-2 py-1 text-[10px] text-sky-200 disabled:opacity-40">Paste style</button>
                </div>
                <div class="mt-3 grid grid-cols-2 gap-2 border-t border-sky-500/20 pt-2">
                  <label class="text-[10px] text-neutral-400">Scale
                    <input type="number" min="1" max="3" step="0.01" bind:value={batchScale} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100" />
                  </label>
                  <label class="text-[10px] text-neutral-400">Position X
                    <input type="number" min="-1" max="1" step="0.01" bind:value={batchPosX} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100" />
                  </label>
                  <label class="text-[10px] text-neutral-400">Position Y
                    <input type="number" min="-1" max="1" step="0.01" bind:value={batchPosY} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100" />
                  </label>
                  <div class="flex items-end">
                    <button type="button" onclick={() => void resetBatchTransform()} disabled={styleBusy} class="w-full rounded border border-neutral-600 px-2 py-1 text-[10px] text-neutral-300 disabled:opacity-40">Reset transform</button>
                  </div>
                  <label class="text-[10px] text-neutral-400">Transition
                    <select bind:value={batchTransitionType} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100">
                      <option value="none">cut</option>
                      <option value="crossfade">crossfade</option>
                      <option value="fade_to_black">fade to black</option>
                    </select>
                  </label>
                  <label class="text-[10px] text-neutral-400">Frames
                    <input type="number" min="1" max="120" step="1" bind:value={batchTransitionFrames} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100" />
                  </label>
                  <label class="text-[10px] text-neutral-400">Fade in (s)
                    <input type="number" min="0" step="0.05" bind:value={batchFadeIn} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100" />
                  </label>
                  <label class="text-[10px] text-neutral-400">Fade out (s)
                    <input type="number" min="0" step="0.05" bind:value={batchFadeOut} class="mt-1 block w-full rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100" />
                  </label>
                  <div class="col-span-2">
                    <button type="button" onclick={() => void applyBatchStyle()} disabled={styleBusy} class="w-full rounded border border-sky-500/40 px-2 py-1 text-[10px] text-sky-200 disabled:opacity-40">{styleBusy ? "Applying…" : "Apply to selected"}</button>
                  </div>
                </div>
              </div>
            {/if}
              {#if selectedClip}
                <div class="rounded-xl border border-violet-500/20 bg-violet-950/10 p-3" data-testid="timeline-effects">
                  <p class="text-[10px] uppercase tracking-wide text-violet-300">Clip effects</p>
                  <div class="mt-2 flex gap-1">
                  <button type="button" onclick={copyClipStyle} class="rounded border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300" title="Copy transition, scale, position, and fades">Copy style</button>
                  <button type="button" onclick={() => void pasteClipStyle()} disabled={!copiedStyle || styleBusy} class="rounded border border-sky-500/40 px-2 py-1 text-[10px] text-sky-200 disabled:opacity-40" title="Paste style to the selected clip(s)">Paste style</button>
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
                </div>
              {:else if selectedIds.length <= 1}
                <div class="rounded-xl border border-dashed border-neutral-800 p-3 text-[10px] text-neutral-500">
                  Select a clip on the canvas to apply effects.
                </div>
              {/if}
              <div class="rounded-xl border border-violet-500/20 bg-violet-950/10 p-3">
                <p class="text-[10px] uppercase tracking-wide text-violet-300">More effects</p>
                <p class="mt-1 text-[10px] text-neutral-400">Reserved for future clip effects.</p>
                <div class="mt-2 grid grid-cols-2 gap-1 text-[9px] text-neutral-500">
                  <span class="rounded border border-neutral-800 px-2 py-1">Colour</span>
                  <span class="rounded border border-neutral-800 px-2 py-1">Blur</span>
                  <span class="rounded border border-neutral-800 px-2 py-1">Crop</span>
                  <span class="rounded border border-neutral-800 px-2 py-1">Mask</span>
                </div>
              </div>
            {/snippet}
          </TimelineInspector>
        </div>
        <div class="group mt-2 flex h-3 cursor-row-resize items-center justify-center rounded-full border border-neutral-800 bg-neutral-900/60" role="separator" aria-label="Resize preview vertically" data-testid="preview-height-resize" onpointerdown={beginPreviewHeightResize}>
          <span class="h-0.5 w-12 rounded-full bg-neutral-600 group-hover:bg-sky-400"></span>
        </div>
      </div>
    <div class="group flex h-3 cursor-row-resize items-center justify-center rounded-full border border-neutral-800 bg-neutral-900/60" role="separator" aria-label="Resize timeline vertically" data-testid="timeline-resize" onpointerdown={beginTimelineResize}>
      <span class="h-0.5 w-12 rounded-full bg-neutral-600 group-hover:bg-sky-400"></span>
    </div>
    <section class="overflow-y-auto rounded-2xl border border-neutral-800 bg-neutral-950" style={`height:${timelineHeight}px`}>
      <div class="flex flex-wrap items-center gap-2 border-b border-neutral-800 px-3 py-2">
        <button type="button" onclick={() => seek(0)} disabled={!timeline} class="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-700 text-neutral-300 disabled:opacity-40" title="Go to start (Home)" aria-label="Go to start"><Icon name="skip-back" size={14} /></button>
        <button type="button" onclick={() => seekSegment(-1)} disabled={!timeline} class="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-700 text-neutral-300 disabled:opacity-40" title="Previous segment (Shift+J)" aria-label="Previous segment"><Icon name="chevron-left" size={14} /></button>
        <button type="button" onclick={togglePlay} disabled={!canPreview} class="flex h-8 w-8 items-center justify-center rounded-lg border border-sky-500/40 bg-sky-500/10 text-sky-200 disabled:opacity-40" title={playing ? "Pause (Space)" : "Play (Space)"} aria-label={playing ? "Pause" : "Play"}><Icon name={playing ? "pause" : "play"} size={14} /></button>
        <button type="button" onclick={() => seekSegment(1)} disabled={!timeline} class="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-700 text-neutral-300 disabled:opacity-40" title="Next segment (Shift+L)" aria-label="Next segment"><Icon name="chevron-right" size={14} /></button>
        <button type="button" onclick={() => seek(duration)} disabled={!timeline} class="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-700 text-neutral-300 disabled:opacity-40" title="Go to end (End)" aria-label="Go to end"><Icon name="skip-forward" size={14} /></button>
        <button type="button" onclick={() => jumpMarker(-1)} disabled={!timeline?.markers.length} class="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-700 text-neutral-300 disabled:opacity-40" title="Previous marker (Alt+Left)" aria-label="Previous marker"><Icon name="bookmark" size={13} /></button>
        <button type="button" onclick={() => jumpMarker(1)} disabled={!timeline?.markers.length} class="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-700 text-neutral-300 disabled:opacity-40" title="Next marker (Alt+Right)" aria-label="Next marker"><Icon name="bookmark" size={13} /></button>
        <select value={String(playbackRate)} onchange={(event) => setPlaybackRate(Number(event.currentTarget.value))} class="h-8 w-[68px] rounded-lg border border-neutral-700 bg-neutral-950 px-1 font-mono text-[10px] text-neutral-300" title="Playback speed" aria-label="Playback speed">
          {#each [1, 1.5, 2, 2.5, 3] as value}
            <option value={String(value)}>{value.toFixed(1)}x</option>
          {/each}
        </select>
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
        <div class="flex rounded-lg border border-neutral-700 bg-neutral-950 p-0.5" role="group" aria-label="Timeline view">
          <button type="button" aria-pressed={viewMode === "normal"} onclick={() => setViewMode("normal")} class={`rounded px-2 py-1 text-[10px] ${viewMode === "normal" ? "bg-sky-500/20 text-sky-200" : "text-neutral-400 hover:text-neutral-200"}`}>Normal</button>
          <button type="button" aria-pressed={viewMode === "recut"} onclick={() => setViewMode("recut")} class={`rounded px-2 py-1 text-[10px] ${viewMode === "recut" ? "bg-rose-500/20 text-rose-200" : "text-neutral-400 hover:text-neutral-200"}`}>Recut</button>
        </div>
        <button type="button" onclick={() => void undo()} disabled={!timeline.can_undo || editBusy} class="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-700 text-neutral-300 disabled:opacity-40" title="Undo (Ctrl+Z)" aria-label="Undo"><Icon name="undo" size={14} /></button>
        <button type="button" onclick={() => void redo()} disabled={!timeline.can_redo || editBusy} class="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-700 text-neutral-300 disabled:opacity-40" title="Redo (Ctrl+Shift+Z)" aria-label="Redo"><Icon name="redo" size={14} /></button>
        {#if selectedIds.length > 1}<span class="rounded bg-sky-500/10 px-2 py-1 text-[10px] text-sky-200">{selectedIds.length} selected</span>{/if}
        <button type="button" onclick={splitSelected} disabled={(!selectedClip && !clipUnderPlayhead) || editBusy} class="flex h-8 w-8 items-center justify-center rounded-lg border border-violet-500/40 text-violet-200 disabled:opacity-40" title="Split selected clip at playhead (S)" aria-label="Split"><Icon name="scissors" size={14} /></button>
        <button type="button" onclick={() => deleteSelected(false)} disabled={!selectedIds.length && !selectedClip || editBusy} class="flex h-8 w-8 items-center justify-center rounded-lg border border-rose-500/40 text-rose-200 disabled:opacity-40" title="Delete selected clip (Delete)" aria-label="Delete"><Icon name="trash" size={14} /></button>
        <button type="button" onclick={() => deleteSelected(true)} disabled={!selectedIds.length && !selectedClip || editBusy} class="flex h-8 w-8 items-center justify-center rounded-lg border border-rose-500/30 text-rose-300 disabled:opacity-40" title="Delete and close the gap (Shift+Delete)" aria-label="Ripple delete"><Icon name="arrow-up" size={14} /></button>
        <button type="button" onclick={() => selectedClip && void toggleSegment(selectedClip.id, false)} disabled={!selectedClip || editBusy} class="rounded-lg border border-rose-500/40 px-2 py-1 text-[10px] text-rose-200 disabled:opacity-40" title="Keep the clip but mark it inactive">Deactivate</button>
        <label class="ml-auto flex items-center gap-1.5 text-[10px] text-neutral-500">
          <input type="checkbox" bind:checked={snap} class="h-3.5 w-3.5 rounded border-neutral-700 bg-neutral-800" />
          Snap
        </label>
        <label class="flex items-center gap-1.5 text-[10px] text-neutral-500" title="Scroll the timeline with the playing cursor">
          <input
            type="checkbox"
            checked={followPlayhead}
            onchange={(event) => setFollowPlayhead(event.currentTarget.checked)}
            class="h-3.5 w-3.5 rounded border-neutral-700 bg-neutral-800"
            aria-label="Follow playhead"
            data-testid="follow-playhead"
          />
          Follow
        </label>
        <button type="button" onclick={markIn} class="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-700 text-neutral-300" title="Mark in (I)" aria-label="Mark in"><Icon name="mark-in" size={14} /></button>
        <button type="button" onclick={markOut} class="flex h-8 w-8 items-center justify-center rounded-lg border border-neutral-700 text-neutral-300" title="Mark out (O)" aria-label="Mark out"><Icon name="mark-out" size={14} /></button>
        <button type="button" onclick={clearMarks} disabled={inPoint === null && outPoint === null} class="rounded-lg border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 disabled:opacity-40" title="Clear in/out marks" aria-label="Clear marks">Clear marks</button>
        <button type="button" onclick={fitTimeline} class="rounded-lg border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300" title="Fit whole timeline (F)">Fit</button>
        <button type="button" onclick={fitSelection} class="rounded-lg border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300" title="Fit selection (Shift+F)">Fit selection</button>
        <label class="flex items-center gap-2 text-[10px] text-neutral-500">
          Zoom
          <input type="range" min="2" max="400" step="1" bind:value={zoom} data-testid="timeline-zoom" class="w-24 accent-sky-400" />
          <span class="w-9 text-right font-mono text-neutral-400">{Math.round(zoom)}</span>
        </label>
      </div>

      <div class="flex flex-wrap gap-2 border-b border-neutral-800 px-3 py-1.5">
        <div class="ml-auto flex flex-wrap items-center gap-1">
          <button type="button" onclick={() => void renderTimeline()} disabled={renderBusy || !selected} class="rounded border border-emerald-500/40 px-2 py-0.5 text-[10px] text-emerald-200 disabled:opacity-40">{renderBusy ? `Rendering ${renderPercent}%` : "Render MP4"}</button>
          {#if renderBusy}<button type="button" onclick={() => void stopRender()} class="rounded border border-rose-500/30 px-1.5 py-0.5 text-[10px] text-rose-300">Cancel</button>{/if}
          {#if renderReady}<a href={renderFileUrl(selected)} download class="rounded border border-emerald-500/40 px-1.5 py-0.5 text-[10px] text-emerald-200">Download</a>{/if}
          <input bind:value={markerLabel} placeholder="Marker label" class="w-28 rounded border border-neutral-800 bg-neutral-950 px-1.5 py-0.5 text-[10px] text-neutral-200" />
          <button type="button" onclick={() => void addMarker()} class="rounded border border-sky-500/40 px-2 py-0.5 text-[10px] text-sky-200">+ Marker</button>
          {#if renderBusy}<span class="text-[9px] text-neutral-500">{renderMessage}</span>{/if}
        </div>
      </div>

      <TimelineAssetRail {assets} />

      {#if !timeline.video.length}
        <div class="mx-3 mb-2 rounded-xl border border-amber-400/20 bg-amber-950/20 px-3 py-2 text-[10px] text-amber-200" data-testid="timeline-empty">
          The timeline is loaded but has no active video segments. Re-run the timeline step or activate an inactive segment.
        </div>
      {/if}
      {#if viewMode === "recut"}
        <RecutCanvas
          {timeline}
          jobId={selected}
          bind:zoom={zoom}
          selectedId={selectedInactiveId || selectedClip?.id || ""}
          busy={editBusy}
          playhead={recutPlayhead}
          {waveforms}
          tracks={timeline.tracks ?? {}}
          onselect={selectRecut}
          ontoggle={toggleSegment}
          ontrim={(id, start, end) => void trimInactiveRange(id, start, end)}
          onseek={recutSeek}
          onToggleTrack={toggleTrack}
        />
      {:else}
      <TimelineCanvas
          {timeline}
          jobId={selected}
          markers={timeline.markers ?? []}
          tracks={timeline.tracks ?? {}}
          {playhead}
          {inPoint}
          {outPoint}
          {zoom}
          selectedClipId={selectedClip?.id ?? ""}
          {selectedIds}
          {snap}
          {brollApproved}
          {waveforms}
          onSeek={seek}
          onSelectClip={selectClip}
          onToggleTrack={toggleTrack}
          onMoveClips={(ids, delta) => {
            void applyBatch(ids.map((id) => ({ clip_id: id, action: "move", delta_sec: delta })));
          }}
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
          onGroupTrim={(ids, edge, delta) => {
            const clips = (timeline?.video ?? []).filter((clip) => ids.includes(clip.id));
            const edits = groupTrimEdits(clips, edge, delta, timeline?.duration_sec ?? 0);
            if (edits.length) void applyBatch(edits as unknown as Array<Record<string, unknown>>);
          }}
          onRippleTrimClip={(id, start, end) => {
            void applyEdit("ripple_trim", { start_sec: start, end_sec: end });
          }}
          onSlipClip={(id, delta) => {
            const clip = timeline?.video.find((item) => item.id === id) ?? null;
            if (clip) {
              selectClip(clip);
              void applyEdit("slip", { delta_sec: delta });
            }
          }}
          onContextMenu={(clip, x, y) => {
            selectClip(clip);
            clipMenu = { x, y, clipId: clip.id };
          }}
          onDropAsset={(asset, time) => void dropAsset(asset, time)}
          onZoom={(value) => (zoom = value)}
        />
      {/if}

      {#if viewMode === "recut" && selectedInactive}
        <TimelineRecutSelection
          inactive={selectedInactive}
          bind:start={inactiveStart}
          bind:end={inactiveEnd}
          {editBusy}
          onApply={trimInactiveRange}
          onActivate={(id) => void toggleSegment(id, true)}
        />
      {/if}

    </section>
      </div>

    {#if clipMenu}
      <div class="fixed z-[70] w-44 overflow-hidden rounded-xl border border-neutral-700 bg-neutral-950 text-[11px] shadow-2xl" style={`left:${clipMenu.x}px;top:${clipMenu.y}px`} role="menu">
        <button type="button" class="block w-full px-3 py-1.5 text-left text-neutral-300 hover:bg-white/5" onclick={() => { clipMenu = null; splitSelected(); }}>Split at playhead</button>
        <button type="button" class="block w-full px-3 py-1.5 text-left text-neutral-300 hover:bg-white/5" onclick={() => { clipMenu = null; void applyEdit("duplicate"); }}>Duplicate</button>
        <button type="button" class="block w-full px-3 py-1.5 text-left text-neutral-300 hover:bg-white/5" onclick={() => { clipMenu = null; deleteSelected(false); }}>Delete</button>
        <button type="button" class="block w-full px-3 py-1.5 text-left text-neutral-300 hover:bg-white/5" onclick={() => { clipMenu = null; deleteSelected(true); }}>Ripple delete</button>
        <button type="button" class="block w-full px-3 py-1.5 text-left text-rose-200 hover:bg-white/5" onclick={() => { const clip = clipMenu?.clipId; clipMenu = null; if (clip) void toggleSegment(clip, false); }}>Deactivate clip</button>
        <button type="button" class="block w-full px-3 py-1.5 text-left text-neutral-300 hover:bg-white/5" onclick={() => { clipMenu = null; void applyEdit("slide", { delta_sec: clipDelta }); }}>Slide {clipDelta}s</button>
        <button type="button" class="block w-full px-3 py-1.5 text-left text-neutral-300 hover:bg-white/5" onclick={() => { clipMenu = null; void addMarker(); }}>Add marker here</button>
        <button type="button" class="block w-full px-3 py-1.5 text-left text-neutral-500 hover:bg-white/5" onclick={() => { clipMenu = null; void refreshComments(); }}>Properties / comments</button>
      </div>
      <button type="button" class="fixed inset-0 z-[60] cursor-default" aria-label="Close clip menu" onclick={() => (clipMenu = null)}></button>
    {/if}

    <Modal
      open={snapshotOpen}
      title="Timeline versions"
      description="Save the current timeline or load an earlier version. Files can also be selected in a timeline.load recipe node."
      width="w-[min(760px,96vw)]"
      onclose={() => (snapshotOpen = false)}
    >
      <div class="flex flex-wrap items-center gap-2 border-b border-neutral-800 pb-3">
        <input
          bind:value={snapshotName}
          placeholder="Version name (optional)"
          class="min-w-[220px] flex-1 rounded-lg border border-neutral-700 bg-neutral-950 px-2 py-1.5 text-xs text-neutral-100"
        />
        <button type="button" onclick={() => void saveVersion()} disabled={snapshotBusy || !selected} class="flex items-center gap-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs text-emerald-200 disabled:opacity-40">
          <Icon name="save" size={14} /> Save version
        </button>
        <label class="flex cursor-pointer items-center gap-1.5 rounded-lg border border-neutral-700 px-3 py-1.5 text-xs text-neutral-300">
          <Icon name="folder" size={14} /> Import JSON
          <input type="file" accept="application/json,.json" class="hidden" onchange={importVersion} />
        </label>
      </div>
      <div class="mt-3 space-y-1.5">
        {#each snapshots as snapshot (snapshot.id)}
          <div class="flex flex-wrap items-center gap-2 rounded-xl border border-neutral-800 bg-white/[0.02] px-3 py-2">
            <div class="min-w-0 flex-1">
              <p class="truncate text-xs font-medium text-neutral-200">{snapshot.name}</p>
              <p class="mt-0.5 truncate font-mono text-[9px] text-neutral-500">
                {snapshot.created_at} · rev {snapshot.revision} · {snapshot.duration_sec.toFixed(2)}s
              </p>
              <p class="mt-0.5 truncate font-mono text-[9px] text-neutral-600">{snapshot.path}</p>
            </div>
            <button type="button" onclick={() => void loadVersion(snapshot)} disabled={snapshotBusy} class="rounded-lg border border-sky-500/40 bg-sky-500/10 px-2.5 py-1 text-[10px] text-sky-200 disabled:opacity-40">Load</button>
            <a href={timelineSnapshotFileUrl(snapshot.id)} download class="rounded-lg border border-neutral-700 px-2.5 py-1 text-[10px] text-neutral-300" title="Download timeline JSON">JSON</a>
            <button type="button" onclick={() => useInRecipe(snapshot)} disabled={snapshotBusy} class="rounded-lg border border-violet-500/40 bg-violet-500/10 px-2.5 py-1 text-[10px] text-violet-200 disabled:opacity-40">Use in recipe</button>
            <button type="button" onclick={() => void removeVersion(snapshot)} disabled={snapshotBusy} class="flex h-7 w-7 items-center justify-center rounded-lg border border-rose-500/30 text-rose-300 disabled:opacity-40" title="Delete version" aria-label={`Delete ${snapshot.name}`}><Icon name="trash" size={12} /></button>
          </div>
        {/each}
        {#if !snapshots.length}<p class="rounded-xl border border-dashed border-neutral-800 px-3 py-8 text-center text-xs text-neutral-500">No saved versions yet.</p>{/if}
      </div>
    </Modal>

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
        <div class="flex items-center gap-2">
          {#if previewDirty}
            <span class="rounded-full border border-amber-400/25 bg-amber-400/10 px-2 py-0.5 text-[9px] uppercase tracking-wide text-amber-200">preview outdated</span>
          {/if}
          <label class="flex items-center gap-1.5 text-[10px] text-neutral-400">
            <input type="checkbox" bind:checked={autoPreview} class="h-3 w-3 accent-sky-500" />
            Auto preview
          </label>
          <button type="button" onclick={() => void buildPreview()} disabled={previewBusy || !selected} class="rounded-lg border border-neutral-700 px-2.5 py-1 text-[10px] text-neutral-300 disabled:opacity-40">{previewBusy ? "Rendering…" : "Rebuild preview"}</button>
        </div>
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
                    <button type="button" onclick={() => moveBroll(title, index, -1)} class="rounded px-1 text-[10px] text-neutral-500 hover:text-white" aria-label="Move B-roll up"><Icon name="arrow-up" size={11} /></button>
                    <button type="button" onclick={() => moveBroll(title, index, 1)} class="rounded px-1 text-[10px] text-neutral-500 hover:text-white" aria-label="Move B-roll down"><Icon name="arrow-down" size={11} /></button>
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
          <div class="mt-3 space-y-1">
            {#each reviewComments as comment}
              <div class="rounded bg-neutral-900/70 px-2 py-1 text-[10px] text-neutral-300">
                <span class="text-neutral-500">{comment.author}{comment.time_sec !== null ? ` @ ${comment.time_sec.toFixed(2)}s` : ""}: </span>{comment.text}
              </div>
            {/each}
            <div class="flex gap-1">
              <input bind:value={commentDraft} placeholder="Review comment" class="min-w-0 flex-1 rounded border border-neutral-700 bg-neutral-950 px-1.5 py-1 text-[10px] text-neutral-100" />
              <button type="button" onclick={() => void addComment()} disabled={!commentDraft.trim()} class="rounded border border-neutral-700 px-2 py-1 text-[10px] text-neutral-300 disabled:opacity-40">Add</button>
            </div>
          </div>
        </div>
        <div class="rounded-xl border border-neutral-800 bg-neutral-950/50 p-3">
          <p class="text-[10px] uppercase tracking-wide text-neutral-500">Thumbnail A/B</p>
          {#if thumbnails.variants.length}
            <div class="mt-2 grid grid-cols-3 gap-2">
              {#each thumbnails.variants as variant}
                {@const metric = thumbMetrics.find((item) => item.name === variant)}
                <div class="space-y-1">
                  <button type="button" onclick={() => void chooseThumbnail(variant)} class={`w-full overflow-hidden rounded border ${thumbnails.selected === variant ? "border-sky-400 ring-1 ring-sky-400" : "border-neutral-800"}`}>
                    <img src={jobThumbnailUrl(selected, variant)} alt={variant} class="aspect-video w-full object-cover" />
                    <span class="block truncate px-1 py-0.5 text-[8px] text-neutral-400">{variant}</span>
                  </button>
                  <div class="flex items-center gap-1 text-[8px] text-neutral-500">
                    <span>CTR {(metric?.ctr ?? 0).toFixed(2)}</span>
                    <button type="button" onclick={() => void bumpMetric(variant, "impressions")} class="rounded bg-neutral-800 px-1">+imp</button>
                    <button type="button" onclick={() => void bumpMetric(variant, "clicks")} class="rounded bg-neutral-800 px-1">+click</button>
                  </div>
                </div>
              {/each}
            </div>
          {:else}
            <p class="mt-2 text-[10px] text-neutral-600">No thumbnail variants. Add a <span class="font-mono">thumbnail.generate</span> step with <span class="font-mono">variants</span>.</p>
          {/if}
        </div>
      </div>

      <TimelineVariantCompare
        {variants}
        busy={variantBusy}
        onLoad={loadVariants}
        onPick={pickWinner}
      />
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
